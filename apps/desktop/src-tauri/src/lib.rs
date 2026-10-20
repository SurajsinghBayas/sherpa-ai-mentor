/// The desktop shell: one window showing the Sherpa web app, which talks to the API over HTTP.
/// All product logic lives in apps/web and the API; this only hosts it and opens external links.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .run(tauri::generate_context!())
        .expect("error while running Sherpa AI");
}
