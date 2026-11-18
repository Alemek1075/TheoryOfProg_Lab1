const vscode = require("vscode");

function activate(context) {
  // the adapter is the Python package, VS Code talks to it over stdin/stdout
  const factory = {
    createDebugAdapterDescriptor() {
      const python = vscode.workspace.getConfiguration("sipl").get("python") || "python";
      return new vscode.DebugAdapterExecutable(python, ["-m", "sipl.dap"]);
    },
  };

  // F5 without launch.json: debug the file that is open
  const provider = {
    resolveDebugConfiguration(folder, config) {
      if (!config.type && !config.request && !config.name) {
        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document.languageId === "sipl") {
          config.type = "sipl";
          config.name = "Debug SIPL";
          config.request = "launch";
          config.program = "${file}";
          config.stopOnEntry = true;
        }
      }
      if (!config.program) {
        vscode.window.showErrorMessage("Відкрий файл .sipl або вкажи program в launch.json");
        return undefined;
      }
      return config;
    },
  };

  context.subscriptions.push(
    vscode.debug.registerDebugAdapterDescriptorFactory("sipl", factory),
    vscode.debug.registerDebugConfigurationProvider("sipl", provider)
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
