import "dotenv/config";
import http from "http";
import { WebSocketServer } from "ws";
import { createApp } from "./app.js";
import { registerLiveWs } from "./websocket/live.js";

const PORT = Number(process.env.PORT || 5000);

const app = createApp();
const server = http.createServer(app);

const wss = new WebSocketServer({ server, path: "/ws" });
registerLiveWs(wss);

server.listen(PORT, () => {
  console.log(`[api] listening on :${PORT}`);
});

