use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::Manager;

struct EngineProcess(Mutex<Option<Child>>);

fn pythonpath_for_root(root: &Path) -> String {
    let sep = if cfg!(windows) { ";" } else { ":" };
    [root.join("cli"), root.join("server"), root.join("engine")]
        .into_iter()
        .map(|p| p.display().to_string())
        .collect::<Vec<_>>()
        .join(sep)
}

fn engine_cmd_candidates() -> Vec<String> {
    let mut out = Vec::new();
    if let Ok(cmd) = std::env::var("CARRO_ENGINE_CMD") {
        out.push(cmd);
    }
    if let Ok(root) = std::env::var("CARRO_ROOT") {
        let root = PathBuf::from(root);
        #[cfg(windows)]
        out.push(
            root.join(".venv")
                .join("Scripts")
                .join("python.exe")
                .display()
                .to_string(),
        );
        #[cfg(not(windows))]
        out.push(root.join(".venv").join("bin").join("python").display().to_string());
    }
    #[cfg(windows)]
    {
        out.push("python".into());
        out.push("py".into());
    }
    #[cfg(not(windows))]
    {
        out.push("python3".into());
        out.push("python".into());
    }
    out
}

fn is_python_launcher(cmd: &str) -> bool {
    let name = Path::new(cmd)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(cmd)
        .to_ascii_lowercase();
    name == "python"
        || name == "python3"
        || name == "python.exe"
        || name == "python3.exe"
        || name == "py"
        || name == "py.exe"
        || name.starts_with("python")
}

fn start_engine(app: &tauri::AppHandle) -> Option<Child> {
    // Prefer repo-relative scripts when developing; fall back to PATH.
    let resource = app
        .path()
        .resource_dir()
        .ok()
        .map(|p| p.join("engine-stub"));

    for cmd in engine_cmd_candidates() {
        let mut c = Command::new(&cmd);
        if is_python_launcher(&cmd) {
            let mut args = Vec::new();
            let base = Path::new(&cmd)
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            if base == "py" || base == "py.exe" {
                args.push("-3".into());
            }
            args.extend([
                "-m".into(),
                "uvicorn".into(),
                "carro_engine.main:app".into(),
                "--host".into(),
                "127.0.0.1".into(),
                "--port".into(),
                "8788".into(),
            ]);
            c.args(&args);
            if let Ok(root) = std::env::var("CARRO_ROOT") {
                let root = PathBuf::from(&root);
                c.env("PYTHONPATH", pythonpath_for_root(&root));
                c.current_dir(&root);
            }
        }
        c.stdout(Stdio::null()).stderr(Stdio::null());
        match c.spawn() {
            Ok(child) => {
                log::info!("started carro-engine via {cmd}");
                let _ = resource;
                return Some(child);
            }
            Err(e) => log::warn!("engine start failed ({cmd}): {e}"),
        }
    }
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(EngineProcess(Mutex::new(None)))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            // Auto-start engine when CARRO_ROOT is set (dev / packaged wrapper scripts).
            if std::env::var("CARRO_ROOT").is_ok() || std::env::var("CARRO_ENGINE_CMD").is_ok() {
                let child = start_engine(app.handle());
                if let Some(state) = app.try_state::<EngineProcess>() {
                    *state.0.lock().unwrap() = child;
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<EngineProcess>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
