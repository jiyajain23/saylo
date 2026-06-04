export const useVideoStream = () => {
    const startVideo = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      return stream;
    };
  
    return { startVideo };
  };