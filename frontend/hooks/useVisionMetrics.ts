import { useRef } from "react";

type Posture = "good" | "ok" | "needs_work";
export type VisionMetrics = {
  eye_contact: number;
  posture: Posture;
  movement: number;
  face_present: boolean;
};

type FaceResult = { faceLandmarks: any[] };
type PoseResult = { landmarks: any[] };

type VisionRuntime = {
  faceLandmarker: { detectForVideo: (video: HTMLVideoElement, timestamp: number) => FaceResult };
  poseLandmarker: { detectForVideo: (video: HTMLVideoElement, timestamp: number) => PoseResult };
};

export const useVisionMetrics = (videoRef: React.RefObject<HTMLVideoElement | null>) => {
  const runtimePromiseRef = useRef<Promise<VisionRuntime> | null>(null);
  const lastTimestampRef = useRef<number>(0);
  const lastNoseRef = useRef<{ x: number; y: number } | null>(null);

  async function loadRuntime(): Promise<VisionRuntime> {
    const { FaceLandmarker, FilesetResolver, PoseLandmarker } = await import("@mediapipe/tasks-vision");
    const vision = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm");
    
    const faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        delegate: "GPU"
      },
      runningMode: "VIDEO",
      numFaces: 1
    });

    const poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        delegate: "GPU"
      },
      runningMode: "VIDEO"
    });

    return { faceLandmarker, poseLandmarker };
  }

  function getRuntime(): Promise<VisionRuntime> {
    if (!runtimePromiseRef.current) {
      runtimePromiseRef.current = loadRuntime().catch((err) => {
        runtimePromiseRef.current = null;
        throw err;
      });
    }
    return runtimePromiseRef.current;
  }

  function eyeContactFromFace(landmarks: any[]): number {
    if (!landmarks || landmarks.length === 0) return 0;
    const face = landmarks[0];
    const leftIris = face[468];
    const rightIris = face[473];
    if (!leftIris || !rightIris) return 0.5;
    const avgX = (leftIris.x + rightIris.x) / 2;
    const distFromCenter = Math.abs(avgX - 0.5);
    return Math.max(0, 1 - distFromCenter * 4);
  }

  function postureFromPose(landmarks: any[]): Posture {
    if (!landmarks || landmarks.length === 0) return "ok";
    const pose = landmarks[0];
    const leftShoulder = pose[11];
    const rightShoulder = pose[12];
    if (!leftShoulder || !rightShoulder) return "ok";
    const tilt = Math.abs(leftShoulder.y - rightShoulder.y);
    if (tilt > 0.1) return "needs_work";
    if (leftShoulder.y > 0.8) return "needs_work"; // Slumping
    return "good";
  }

  function movementFromFace(landmarks: any[], lastNose: React.MutableRefObject<{ x: number; y: number } | null>): number {
    if (!landmarks || landmarks.length === 0) return 0;
    const nose = landmarks[0][1];
    if (!nose) return 0;
    if (!lastNose.current) {
      lastNose.current = { x: nose.x, y: nose.y };
      return 0;
    }
    const dx = nose.x - lastNose.current.x;
    const dy = nose.y - lastNose.current.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    lastNose.current = { x: nose.x, y: nose.y };
    return Math.min(1, dist * 50);
  }

  const analyze = async (): Promise<VisionMetrics> => {
    const video = videoRef.current;
    if (!video || video.readyState < 2 || video.videoWidth === 0 || video.videoHeight === 0) {
      return { eye_contact: 0, posture: "ok", movement: 0, face_present: false };
    }

    try {
      const runtime = await getRuntime();
      const now = Math.max(lastTimestampRef.current + 1, performance.now());
      lastTimestampRef.current = now;

      let faceResult: FaceResult | null = null;
      let poseResult: PoseResult | null = null;

      try {
        faceResult = runtime.faceLandmarker.detectForVideo(video, now);
      } catch (e) {
        console.warn("[vision] face detect error", e);
      }

      try {
        poseResult = runtime.poseLandmarker.detectForVideo(video, now);
      } catch (e) {
        console.warn("[vision] pose detect error", e);
      }

      const faceLandmarks = faceResult?.faceLandmarks || [];
      const poseLandmarks = poseResult?.landmarks || [];

      return {
        eye_contact: Number(eyeContactFromFace(faceLandmarks).toFixed(3)),
        posture: postureFromPose(poseLandmarks),
        movement: Number(movementFromFace(faceLandmarks, lastNoseRef).toFixed(3)),
        face_present: Boolean(faceLandmarks?.length)
      };
    } catch (err) {
      console.error("[vision] runtime error", err);
      runtimePromiseRef.current = null;
      return { eye_contact: 0, posture: "ok", movement: 0, face_present: false };
    }
  };

  return { analyze };
};
