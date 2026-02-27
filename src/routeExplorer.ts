import * as vscode from 'vscode';
import { LanguageClient } from 'vscode-languageclient/node';

interface RouteTreeData {
    kind: string;
    label: string;
    path: string;
    fullPath: string;
    httpMethods: string[];
    line: number;
    endLine: number;
    uri: string;
    children: RouteTreeData[];
    guards: string[];
    dependencies: Record<string, string>;
}

const METHOD_ICONS: Record<string, vscode.ThemeIcon> = {
    GET: new vscode.ThemeIcon('arrow-down', new vscode.ThemeColor('charts.green')),
    POST: new vscode.ThemeIcon('arrow-up', new vscode.ThemeColor('charts.yellow')),
    PUT: new vscode.ThemeIcon('arrow-swap', new vscode.ThemeColor('charts.blue')),
    PATCH: new vscode.ThemeIcon('edit', new vscode.ThemeColor('charts.orange')),
    DELETE: new vscode.ThemeIcon('trash', new vscode.ThemeColor('charts.red')),
    HEAD: new vscode.ThemeIcon('eye', new vscode.ThemeColor('charts.purple')),
};

const KIND_ICONS: Record<string, vscode.ThemeIcon> = {
    app: new vscode.ThemeIcon('server'),
    router: new vscode.ThemeIcon('git-merge'),
    controller: new vscode.ThemeIcon('symbol-class'),
    dependenciesGroup: new vscode.ThemeIcon('symbol-namespace'),
    guardsGroup: new vscode.ThemeIcon('shield'),
    dependency: new vscode.ThemeIcon('symbol-variable'),
    guard: new vscode.ThemeIcon('symbol-method'),
};

class RouteTreeItem extends vscode.TreeItem {
    constructor(
        public readonly data: RouteTreeData,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    ) {
        super(RouteTreeItem.buildLabel(data), collapsibleState);

        this.tooltip = RouteTreeItem.buildTooltip(data);
        this.iconPath = RouteTreeItem.pickIcon(data);
        this.contextValue = data.kind;

        if (data.uri && data.line > 0) {
            const fileUri = vscode.Uri.parse(data.uri);
            this.command = {
                command: 'vscode.open',
                title: 'Go to definition',
                arguments: [
                    fileUri,
                    {
                        selection: new vscode.Range(
                            new vscode.Position(data.line - 1, 0),
                            new vscode.Position(data.line - 1, 0),
                        ),
                    },
                ],
            };
        }
    }

    private static buildLabel(data: RouteTreeData): string {
        if (data.kind === 'handler') {
            const methods = data.httpMethods.join(', ');
            return `${methods} ${data.fullPath}`;
        }
        if (data.kind === 'controller') {
            return `${data.label} [${data.path || '/'}]`;
        }
        if (data.kind === 'router') {
            return `${data.label} [${data.path || '/'}]`;
        }
        return data.label;
    }

    private static buildTooltip(data: RouteTreeData): string {
        const parts: string[] = [];
        if (data.kind === 'handler') {
            parts.push(`${data.httpMethods.join(', ')} ${data.fullPath}`);
            parts.push(`Handler: ${data.label}`);
        } else {
            parts.push(`${data.kind}: ${data.label}`);
            if (data.path) {
                parts.push(`Path: ${data.path}`);
            }
        }
        if (data.guards.length > 0) {
            parts.push(`Guards: ${data.guards.join(', ')}`);
        }
        const depKeys = Object.keys(data.dependencies);
        if (depKeys.length > 0) {
            parts.push(`Dependencies: ${depKeys.join(', ')}`);
        }
        return parts.join('\n');
    }

    private static pickIcon(data: RouteTreeData): vscode.ThemeIcon | undefined {
        if (data.kind === 'handler' && data.httpMethods.length > 0) {
            return METHOD_ICONS[data.httpMethods[0]] ?? new vscode.ThemeIcon('symbol-method');
        }
        return KIND_ICONS[data.kind] ?? new vscode.ThemeIcon('symbol-misc');
    }
}

export class RouteTreeProvider implements vscode.TreeDataProvider<RouteTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<RouteTreeItem | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private _treeData: RouteTreeData[] = [];
    private _client: LanguageClient | undefined;

    setClient(client: LanguageClient | undefined): void {
        this._client = client;
    }

    async refresh(): Promise<void> {
        if (!this._client || this._client.state !== 2 /* Running */) {
            this._treeData = [];
            this._onDidChangeTreeData.fire();
            return;
        }
        try {
            const data = await this._client.sendRequest<RouteTreeData[]>('litestar/routes', {});
            this._treeData = data ?? [];
        } catch {
            this._treeData = [];
        }
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: RouteTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: RouteTreeItem): RouteTreeItem[] {
        if (!element) {
            return this._treeData.map((item) => this.toTreeItem(item));
        }

        const data = element.data;

        // Synthetic groups: expand to list of dependency or guard entries
        if (data.kind === 'dependenciesGroup' && data.dependencies) {
            return Object.entries(data.dependencies).map(([key, value]) =>
                this.toTreeItem({
                    ...this.emptyNode(),
                    kind: 'dependency',
                    label: `${key} → ${value}`,
                    dependencies: {},
                    guards: [],
                }),
            );
        }
        if (data.kind === 'guardsGroup' && data.guards.length > 0) {
            return data.guards.map((g) =>
                this.toTreeItem({
                    ...this.emptyNode(),
                    kind: 'guard',
                    label: g,
                    dependencies: {},
                    guards: [],
                }),
            );
        }

        // App, router, controller: prepend Dependencies and Guards groups if present
        const hasDeps = data.dependencies && Object.keys(data.dependencies).length > 0;
        const hasGuards = data.guards && data.guards.length > 0;
        const isContainer = data.kind === 'app' || data.kind === 'router' || data.kind === 'controller';

        const children: RouteTreeItem[] = [];
        if (isContainer && hasDeps) {
            children.push(
                this.toTreeItem(
                    {
                        ...this.emptyNode(),
                        kind: 'dependenciesGroup',
                        label: 'Dependencies',
                        dependencies: data.dependencies,
                        guards: [],
                    },
                    vscode.TreeItemCollapsibleState.Collapsed,
                ),
            );
        }
        if (isContainer && hasGuards) {
            children.push(
                this.toTreeItem(
                    {
                        ...this.emptyNode(),
                        kind: 'guardsGroup',
                        label: 'Guards',
                        dependencies: {},
                        guards: data.guards,
                    },
                    vscode.TreeItemCollapsibleState.Collapsed,
                ),
            );
        }
        const routeChildren = (data.children || []).map((item) => this.toTreeItem(item));
        return [...children, ...routeChildren];
    }

    private emptyNode(): RouteTreeData {
        return {
            kind: '',
            label: '',
            path: '',
            fullPath: '',
            httpMethods: [],
            line: 0,
            endLine: 0,
            uri: '',
            children: [],
            guards: [],
            dependencies: {},
        };
    }

    private toTreeItem(item: RouteTreeData, forceState?: vscode.TreeItemCollapsibleState): RouteTreeItem {
        const hasChildren =
            item.children.length > 0 || item.kind === 'dependenciesGroup' || item.kind === 'guardsGroup';
        const state =
            forceState ??
            (hasChildren ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None);
        return new RouteTreeItem(item, state);
    }

    getRawData(): RouteTreeData[] {
        return this._treeData;
    }
}
