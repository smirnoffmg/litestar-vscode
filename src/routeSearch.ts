import * as vscode from 'vscode';
import { RouteTreeProvider } from './routeExplorer';

interface FlatRoute {
    methods: string;
    fullPath: string;
    handlerName: string;
    uri: string;
    line: number;
}

function collectRoutes(
    nodes: {
        kind: string;
        label: string;
        fullPath: string;
        httpMethods: string[];
        uri: string;
        line: number;
        children: any[];
    }[],
    out: FlatRoute[],
): void {
    for (const node of nodes) {
        if (node.kind === 'handler') {
            out.push({
                methods: node.httpMethods.join(', '),
                fullPath: node.fullPath,
                handlerName: node.label,
                uri: node.uri,
                line: node.line,
            });
        }
        if (node.children) {
            collectRoutes(node.children, out);
        }
    }
}

export async function searchRoutes(provider: RouteTreeProvider): Promise<void> {
    const rawData = provider.getRawData();
    const routes: FlatRoute[] = [];
    collectRoutes(rawData, routes);

    if (routes.length === 0) {
        vscode.window.showInformationMessage('No Litestar routes found in the workspace.');
        return;
    }

    const items: vscode.QuickPickItem[] = routes.map((r) => {
        const uri = vscode.Uri.parse(r.uri);
        const relativePath = vscode.workspace.asRelativePath(uri);
        return {
            label: `$(symbol-method) [${r.methods}] ${r.fullPath}`,
            description: r.handlerName,
            detail: `${relativePath}:${r.line}`,
        };
    });

    const selected = await vscode.window.showQuickPick(items, {
        placeHolder: 'Search routes by path, method, or handler name...',
        matchOnDescription: true,
        matchOnDetail: true,
    });

    if (!selected) {
        return;
    }

    const idx = items.indexOf(selected);
    const route = routes[idx];

    const fileUri = vscode.Uri.parse(route.uri);
    const doc = await vscode.workspace.openTextDocument(fileUri);
    await vscode.window.showTextDocument(doc, {
        selection: new vscode.Range(new vscode.Position(route.line - 1, 0), new vscode.Position(route.line - 1, 0)),
    });
}
