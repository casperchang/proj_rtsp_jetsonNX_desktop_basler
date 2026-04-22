from flask import Flask, Response
import cv2
from pypylon import pylon
import numpy as np
import time
import yaml

class DualCamera():
    def __init__(self, config_path):
        self._load_config(config_path)

        self.device_num = len(self.settings)

        self.converter = pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned


        # === 相機初始化 ===
        transport_layer_factory = pylon.TlFactory.GetInstance()
        devices = transport_layer_factory.EnumerateDevices()
        if len(devices) < self.device_num:
            print("需要至少兩顆相機")
            exit(1)

        self.cameras = pylon.InstantCameraArray(self.device_num)
        for i, camera in enumerate(self.cameras):
            camera.Attach(transport_layer_factory.CreateDevice(devices[i]))

        self.cameras.Open()

        for idx, cam in enumerate(self.cameras):
            print(f"set context {idx} for camera {cam.DeviceInfo.GetSerialNumber()}")
            setting = self.settings[idx]
            cam.SetCameraContext(idx)
            cam.ExposureTime.SetValue(setting.get('ExposureTime', 7500))
            cam.AcquisitionFrameRateEnable.SetValue(True)
            cam.AcquisitionFrameRate.SetValue(30.0)
            cam.Width.SetValue(1600)
            cam.Height.SetValue(1200)
            cam.BslCenterX.Execute()
            cam.BslCenterY.Execute()
            cam.Gain.Value = setting.get('Gain', 0.0)
            cam.PixelFormat.Value = "BayerRG8"
            cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

        self.camera1 = self.cameras[0]
        self.camera2 = self.cameras[1]



    def get_cameras(self):
        return self.cameras

    def get_image(self, camera):
        if camera.IsGrabbing():
            try:
                grab_result = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
                if grab_result.GrabSucceeded():
                    img = self.converter.Convert(grab_result)
                    image = img.Array
                    # print the shape of the image
                    # print(f"Image shape: {image.shape}")
                    # image_resize = cv2.resize(image, (1024, 768))
                    image_resize = image.copy()
                    ret, buffer = cv2.imencode('.jpg', image_resize)
                    frame_bytes = buffer.tobytes()
                    return frame_bytes
                    # yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                grab_result.Release()
            except Exception as e:
                print(f"[get_frame] exception: {e}")
        return None

    def release(self):
        print("\nStopping cameras...")
        for camera in self.cameras:
            if camera.IsGrabbing():
                camera.StopGrabbing()
            if camera.IsOpen():
                camera.Close()
        print("All cameras released.")


    def _load_config(self, path):
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
        self.settings = config.get('CameraSettings', [])


# camera1 = cameras[0]
# camera2 = cameras[1]

