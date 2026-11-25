// The installed Chrome, driven headless by playwright-core (no browser download).
// Headless only: nothing here touches the real mouse, keyboard focus or windows.
import { existsSync } from "node:fs";

const candidates = [process.env.CHROME_PATH, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium-browser", "/usr/bin/chromium",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].filter(Boolean);
export const CHROME = candidates.find(p => existsSync(p));
if (!CHROME) throw new Error("Chrome을 찾지 못함. CHROME_PATH 환경 변수로 실행 파일 경로를 지정: " + candidates.join(", "));
