import { logger } from "./logger.js";

/**
 * A simple in-memory store for raw audio chunks during a live session.
 * Chunks are stored as Base64 strings (as received from the client) and 
 * concatenated only when requested for analysis.
 */
class AudioBufferStore {
  private buffers = new Map<string, string[]>();

  append(sessionId: string, base64Chunk: string) {
    if (!this.buffers.has(sessionId)) {
      this.buffers.set(sessionId, []);
    }
    this.buffers.get(sessionId)?.push(base64Chunk);
  }

  /**
   * Concatenates all chunks for a session into a single Base64 string.
   * Note: This assumes all chunks are valid PCM chunks that can be 
   * concatenated at the byte level.
   */
  pop(sessionId: string): string | null {
    if (!sessionId) return null;
    const chunks = this.buffers.get(sessionId);
    if (!chunks || chunks.length === 0) return null;
    
    this.buffers.delete(sessionId);
    
    try {
      // Convert all base64 chunks to Buffers, concat, then back to base64
      const buffers = chunks.map(c => Buffer.from(c, 'base64'));
      return Buffer.concat(buffers).toString('base64');
    } catch (err) {
      logger.error("[audio-store] failed to concatenate chunks", { sessionId, err });
      return null;
    }
  }

  clear(sessionId: string) {
    this.buffers.delete(sessionId);
  }
}

export const audioBufferStore = new AudioBufferStore();
