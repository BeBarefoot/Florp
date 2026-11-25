# Debug Florp on a physical Android phone

Florp for Android is an installable Chrome web app. The Next.js app, tour, manifest, icons, service worker, local API and USB setup script are all in the Florp repository. Chrome runs the app on your phone while your computer stores projects and runs extraction.

## Prepare your computer and phone

1. In your Florp checkout, use the current `main` branch. Install Node.js 22, [uv](https://docs.astral.sh/uv/getting-started/installation/), and [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools). On a Mac with Homebrew, you can use `brew install --cask android-platform-tools`.
2. From the Florp repository root, install the locked dependencies and start the development server with hot reload.

   ```bash
   (cd apps/api && uv sync --locked)
   (cd apps/web && npm ci)
   ./scripts/dev.sh
   ```

3. Enable **Developer options** on the phone by tapping **Build number** seven times, then enable **USB debugging**. Connect a USB data cable, unlock your phone, and accept the computer’s debugging prompt. Run `adb devices -l` on your computer and check that the phone shows as `device`.
4. From a second terminal at the repository root, run `./scripts/android-debug.sh`. If several devices are connected, use `./scripts/android-debug.sh DEVICE_SERIAL` with the serial from `adb devices -l`. The script checks the local app and API, then forwards ports 3000 and 8000 to the phone.
5. Open **http://localhost:3000/phone** in Chrome on the phone. Start with **Explore sample tour** to check rendering and gestures. Open or upload a project to check the API. Chrome’s menu offers **Install app** or **Add to Home screen**. Keep the USB connection and both local servers running.

USB forwarding lets the servers stay bound to the computer’s loopback interface. Use the default API URL for USB. If you previously configured `NEXT_PUBLIC_API_URL=/florp-api` for a private HTTPS gateway, remove that override and restart the dev server before using the USB instructions.

## Inspect and debug

- On your computer, open `chrome://inspect/#devices` in Chrome, enable **Discover USB devices**, and click **Inspect** beside the Florp tab. Use **Console** for errors and **Network** to inspect requests to `http://localhost:8000`.
- In the walkthrough, drag two fingers together to move, twist the pair to turn, and pinch to zoom. In Overview, drag one finger to orbit, or use two fingers to pan, twist, and pinch.
- If the phone shows `ERR_CONNECTION_REFUSED`, confirm Florp loads on the computer, run `adb reverse --list`, and rerun the script after reconnecting the phone. If the page loads but projects fail, check port 8000 and open `http://localhost:8000/health` in Chrome on the phone.
- If Chrome shows `unauthorized` in `adb devices -l`, unlock the phone and approve the USB prompt. If the device list is empty, try a different USB data cable or port.
- For a production-build check, stop the dev server and run `./scripts/start.sh`. Repeat the same USB steps after the build starts serving.

Run `adb reverse --remove tcp:3000` and `adb reverse --remove tcp:8000` when you finish debugging. Press **Ctrl+C** in the Florp terminal to stop the servers.
