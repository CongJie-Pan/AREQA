import React, { useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useStore } from '../store/useStore';

const API_BASE = '/api';

/**
 * ScreenObserver runs in the background when recording is active and screen capture is enabled.
 * It asks for display media permissions and periodically captures the screen.
 */
const ScreenObserver: React.FC = () => {
  const { isRecording, enableScreenCapture } = useStore();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<number | null>(null);

  const stopCapture = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const captureAndSendFrame = useCallback(async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !streamRef.current) return;

    // Make sure video has valid dimensions
    if (video.videoWidth === 0 || video.videoHeight === 0) return;

    // Scale down resolution for LLM processing to save tokens and bandwidth
    // Use a max dimension (e.g. 1024px) while maintaining aspect ratio
    const MAX_DIMENSION = 1024;
    let width = video.videoWidth;
    let height = video.videoHeight;
    
    if (width > height && width > MAX_DIMENSION) {
      height = Math.round(height * (MAX_DIMENSION / width));
      width = MAX_DIMENSION;
    } else if (height > width && height > MAX_DIMENSION) {
      width = Math.round(width * (MAX_DIMENSION / height));
      height = MAX_DIMENSION;
    }

    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Draw the current video frame onto the canvas
    ctx.drawImage(video, 0, 0, width, height);

    // Compress the image slightly as JPEG (0.7 quality is a good balance)
    const base64Image = canvas.toDataURL('image/jpeg', 0.7);

    try {
      await axios.post(`${API_BASE}/recording/observation`, {
        type: 'input_image',
        content: base64Image
      });
    } catch (err) {
      console.error('Failed to send observation:', err);
    }
  }, []);

  const startCapture = useCallback(async () => {
    try {
      if (!streamRef.current) {
        const stream = await navigator.mediaDevices.getDisplayMedia({
          video: {
            displaySurface: 'monitor',
          },
          audio: false,
        });
        streamRef.current = stream;

        // Listen for stream stop from browser UI
        stream.getVideoTracks()[0].onended = () => {
          stopCapture();
          // Ideally update store if permission revoked, but simple cleanup for now
        };

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      }

      // 6-second interval per user request
      intervalRef.current = window.setInterval(captureAndSendFrame, 6000);
    } catch (err) {
      console.error('Failed to start screen capture:', err);
    }
  }, [captureAndSendFrame, stopCapture]);

  useEffect(() => {
    // If not recording or screen capture disabled, clean up and exit
    if (!isRecording || !enableScreenCapture) {
      stopCapture();
      return;
    }

    // Start capturing
    startCapture();

    return () => {
      stopCapture();
    };
  }, [isRecording, enableScreenCapture, startCapture, stopCapture]);

  return (
    <div style={{ display: 'none' }}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{ width: '100%', height: '100%' }}
      />
      <canvas ref={canvasRef} />
    </div>
  );
};

export default ScreenObserver;
