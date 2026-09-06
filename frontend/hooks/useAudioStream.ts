export const useAudioStream = () => {
    const startAudio = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      return stream;
    };
  
    return { startAudio };
  };