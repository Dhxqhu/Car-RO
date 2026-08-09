use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::Manager;

struct EngineProcess(Mutex<Option<Child>>);

fn start_engine(app: &tauri::AppHandle) -> Option<Child> {
    // Prefer repo-relative scripts when developing; fall back to PATH.
    let resource = app
        .path()
        .resource_dir()
        .ok()
        .map(|p| p.join("engine-stub"));

    let candidates = [
        std::env::var("CARRO_ENGINE_CMD").ok(),
        Some("python3".into()),
    ];

    for cmd in candidates.into_iter().flatten() {
        let mut c = Command::new(&cmd);
        if cmd == "python3" || cmd.ends_with("python") || cmd.ends_with("python3") {
            c.args(["-m", "uvicorn", "carro_engine.main:app", "--host", "127.0.0.1", "--port", "8788"]);
            if let Ok(root) = std::env::var("CARRO_ROOT") {
                c.env(
                    "PYTHONPATH",
                    format!("{root}/cli:{root}/server:{root}/engine"),
                );
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
