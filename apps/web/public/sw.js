// Only handle page navigation. Project files and API mutations go directly to the server.
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET" || event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() => new Response(
    '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Florp offline</title><main style="font:1rem system-ui;padding:1.5rem"><h1>Florp is offline</h1><p>Reconnect to the computer running Florp to open this page.</p><button onclick="location.reload()">Try again</button></main></html>',
    { status: 503, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } }
  )));
});
