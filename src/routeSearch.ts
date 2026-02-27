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

function routeKey(r: FlatRoute): string {
    return `${r.methods}|${r.fullPath}|${r.uri}|${r.line}`;
}

function dedupeRoutes(routes: FlatRoute[]): FlatRoute[] {
    const seen = new Set<string>();
    return routes.filter((r) => {
        const key = routeKey(r);
        if (seen.has(key)) {
            return false;
        }
        seen.add(key);
        return true;
    });
}

export async function searchRoutes(provider: RouteTreeProvider): Promise<void> {
    const rawData = provider.getRawData();
    const routes: FlatRoute[] = [];
    collectRoutes(rawData, routes);
    const uniqueRoutes = dedupeRoutes(routes);

    if (uniqueRoutes.length === 0) {
        vscode.window.showInformationMessage('No Litestar routes found in the workspace.');
        return;
    }

    const items: vscode.QuickPickItem[] = uniqueRoutes.map((r) => {
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
    const route = uniqueRoutes[idx];

    const fileUri = vscode.Uri.parse(route.uri);
    const doc = await vscode.workspace.openTextDocument(fileUri);
    await vscode.window.showTextDocument(doc, {
        selection: new vscode.Range(new vscode.Position(route.line - 1, 0), new vscode.Position(route.line - 1, 0)),
    });
}
