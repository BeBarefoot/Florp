# Local development

Use the [top-level setup](../README.md#run-on-your-mac) for Node.js, uv and locked dependencies. From the repository root, run `./scripts/dev.sh` for hot reload or `./scripts/start.sh` for a production build served locally. Run both processes on the Mac where you open `http://localhost:3000`. A remote development workspace has its own localhost.

Optional API settings belong in `apps/api/.env`. Use [.env.example](../.env.example) as a reference, and preserve existing keys and paths when updating. The API docs are at [localhost:8000/docs](http://localhost:8000/docs).

See [development and test commands](../README.md#develop-and-test), [phone installation](../README.md#run-and-install-the-smartphone-app), and [optional local image generation](LOCAL_COMFY.md).
