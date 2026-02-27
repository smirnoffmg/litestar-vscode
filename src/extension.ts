import * as vscode from 'vscode';
import { LanguageClient } from 'vscode-languageclient/node';
import { registerLogger, traceError, traceLog, traceVerbose } from './common/log/logging';
import {
    checkVersion,
    getInterpreterDetails,
    initializePython,
    onDidChangePythonInterpreter,
    resolveInterpreter,
} from './common/python';
import { restartServer } from './common/server';
import { checkIfConfigurationChanged, getInterpreterFromSetting, getServerEnabled } from './common/settings';
import { loadServerDefaults } from './common/setup';
import { LS_SERVER_RESTART_DELAY } from './common/constants';
import { getLSClientTraceLevel } from './common/utilities';
import { createOutputChannel, onDidChangeConfiguration, registerCommand } from './common/vscodeapi';
import { RouteTreeProvider } from './routeExplorer';
import { searchRoutes } from './routeSearch';

let lsClient: LanguageClient | undefined;
let isRestarting = false;
let restartTimer: NodeJS.Timeout | undefined;
const routeTreeProvider = new RouteTreeProvider();

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    const serverInfo = loadServerDefaults();
    const serverName = serverInfo.name;
    const serverId = serverInfo.module;

    // Setup logging
    const outputChannel = createOutputChannel(serverName);
    context.subscriptions.push(outputChannel, registerLogger(outputChannel));

    const changeLogLevel = async (c: vscode.LogLevel, g: vscode.LogLevel) => {
        const level = getLSClientTraceLevel(c, g);
        await lsClient?.setTrace(level);
    };

    context.subscriptions.push(
        outputChannel.onDidChangeLogLevel(async (e) => {
            await changeLogLevel(e, vscode.env.logLevel);
        }),
        vscode.env.onDidChangeLogLevel(async (e) => {
            await changeLogLevel(outputChannel.logLevel, e);
        }),
    );

    traceLog(`Name: ${serverInfo.name}`);
    traceLog(`Module: ${serverInfo.module}`);
    traceVerbose(`Full Server Info: ${JSON.stringify(serverInfo)}`);

    // Register Route Explorer tree view
    const treeView = vscode.window.createTreeView('litestarRoutes', {
        treeDataProvider: routeTreeProvider,
        showCollapseAll: true,
    });
    context.subscriptions.push(treeView);

    const runServer = async () => {
        if (isRestarting) {
            if (restartTimer) {
                clearTimeout(restartTimer);
            }
            restartTimer = setTimeout(runServer, LS_SERVER_RESTART_DELAY);
            return;
        }
        isRestarting = true;
        try {
            if (!getServerEnabled(serverId)) {
                if (lsClient) {
                    try {
                        await lsClient.stop();
                    } catch (ex) {
                        traceError(`Server: Stop failed: ${ex}`);
                    }
                    lsClient = undefined;
                }
                routeTreeProvider.setClient(undefined);
                return;
            }

            const interpreter = getInterpreterFromSetting(serverId);
            if (interpreter && interpreter.length > 0) {
                if (checkVersion(await resolveInterpreter(interpreter))) {
                    traceVerbose(`Using interpreter from ${serverInfo.module}.interpreter: ${interpreter.join(' ')}`);
                    lsClient = await restartServer(serverId, serverName, outputChannel, lsClient);
                }
            } else {
                const interpreterDetails = await getInterpreterDetails();
                if (interpreterDetails.path) {
                    traceVerbose(`Using interpreter from Python extension: ${interpreterDetails.path.join(' ')}`);
                    lsClient = await restartServer(serverId, serverName, outputChannel, lsClient);
                } else {
                    traceError(
                        'Python interpreter missing:\r\n' +
                            '[Option 1] Select python interpreter using the ms-python.python.\r\n' +
                            `[Option 2] Set an interpreter using "${serverId}.interpreter" setting.\r\n` +
                            'Please use Python 3.9 or greater.',
                    );
                }
            }

            routeTreeProvider.setClient(lsClient);
            if (lsClient) {
                // Refresh routes once the server is running
                setTimeout(() => routeTreeProvider.refresh(), 1500);
            }
        } finally {
            isRestarting = false;
        }
    };

    context.subscriptions.push(
        onDidChangePythonInterpreter(async () => {
            await runServer();
        }),
        onDidChangeConfiguration(async (e: vscode.ConfigurationChangeEvent) => {
            if (checkIfConfigurationChanged(e, serverId)) {
                await runServer();
            }
        }),
        registerCommand(`${serverId}.restart`, async () => {
            await runServer();
        }),
        registerCommand('litestar.showRoutes', async () => {
            try {
                await vscode.commands.executeCommand('litestar.focus');
            } catch {
                // View may not be visible yet
            }
        }),
        registerCommand('litestar.searchRoutes', async () => {
            await searchRoutes(routeTreeProvider);
        }),
        registerCommand('litestar.refreshRoutes', async () => {
            await routeTreeProvider.refresh();
        }),
        registerCommand('litestar.goToHandler', async (uri: string, line: number) => {
            const fileUri = vscode.Uri.parse(uri);
            const doc = await vscode.workspace.openTextDocument(fileUri);
            await vscode.window.showTextDocument(doc, {
                selection: new vscode.Range(new vscode.Position(line - 1, 0), new vscode.Position(line - 1, 0)),
            });
        }),
    );

    // Refresh routes when files are saved
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(async (doc) => {
            if (doc.languageId === 'python') {
                // Small delay to allow the server to process the change
                setTimeout(() => routeTreeProvider.refresh(), 500);
            }
        }),
    );

    setImmediate(async () => {
        const interpreter = getInterpreterFromSetting(serverId);
        if (interpreter === undefined || interpreter.length === 0) {
            traceLog(`Python extension loading`);
            await initializePython(context.subscriptions);
            traceLog(`Python extension loaded`);
        } else {
            await runServer();
        }
    });
}

export async function deactivate(): Promise<void> {
    if (lsClient) {
        try {
            await lsClient.stop();
        } catch (ex) {
            traceError(`Server: Stop failed: ${ex}`);
        }
    }
}
