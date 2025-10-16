import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';
import 'package:ipad_demo/face_detection_painter.dart';
import 'package:ipad_demo/api_service.dart';
import 'package:permission_handler/permission_handler.dart';
import 'dart:io';
import 'dart:async';
import 'package:image/image.dart' as img;

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  CameraController? _controller;
  Future<void>? _initializeControllerFuture;
  final FaceDetector _faceDetector = FaceDetector(
    options: FaceDetectorOptions(
      enableClassification: true,
      enableLandmarks: true,
      enableTracking: true,
      performanceMode: FaceDetectorMode.fast,
    ),
  );
  bool _isDetecting = false;
  List<Face> _faces = [];
  List<CameraDescription> cameras = [];
  int _selectedCameraIndex = 0;
  CameraImage? _pendingCameraImage; // last frame that HAD a face
  Size? _pendingSize; // raw size of that frame (w,h)
  Face? _pendingFace; // the chosen face for that frame
  late final ValueNotifier<DateTime> _now = ValueNotifier(DateTime.now());
  Timer? _clock;

  @override
  void initState() {
    super.initState();
    _requestPermission();
    _initializeCameras();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      _now.value = DateTime.now();
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    _now.dispose();
    _controller?.dispose();
    _faceDetector.close();
    super.dispose();
  }

  String _fmt(DateTime t) {
    String two(int n) => n.toString().padLeft(2, '0');
    return '${t.year}-${two(t.month)}-${two(t.day)} '
        '${two(t.hour)}:${two(t.minute)}';
  }

  Future<void> _requestPermission() async {
    final status = await Permission.camera.request();
    if (status != PermissionStatus.granted) {
      print("Permission Denied");
    }
  }

  Future<void> _initializeCameras() async {
    try {
      cameras = await availableCameras();
      if (cameras.isEmpty) {
        print("No Cameras Found");
        return;
      }

      _selectedCameraIndex = cameras.indexWhere(
        (camera) => camera.lensDirection == CameraLensDirection.front,
      );
      if (_selectedCameraIndex == -1) {
        _selectedCameraIndex = 0;
      }
      await _initializeCamera(cameras[_selectedCameraIndex]);
    } catch (e) {
      print(e);
    }
  }

  Future<void> _initializeCamera(CameraDescription cameraDescription) async {
    final controller = CameraController(
      cameraDescription,
      ResolutionPreset.ultraHigh,
      enableAudio: false,
      imageFormatGroup:
          Platform.isIOS ? ImageFormatGroup.bgra8888 : ImageFormatGroup.yuv420,
    );

    _controller = controller;

    _initializeControllerFuture = controller
        .initialize()
        .then((_) {
          if (!mounted) return;
          setState(() {
            _startFaceDetection();
          });
        })
        .catchError((error) {
          print(error);
        });
  }

  Face? _selectPrimaryFace(List<Face> faces) {
    if (faces.isEmpty) return null;

    // Largest-area face capture
    faces.sort((a, b) {
      final aArea = a.boundingBox.width * a.boundingBox.height;
      final bArea = b.boundingBox.width * b.boundingBox.height;
      return bArea.compareTo(aArea); // desc
    });
    return faces.first;
  }

  InputImage? _convertCameraImageToInputImage(CameraImage image) {
    if (_controller == null) return null;
    try {
      final format =
          Platform.isIOS ? InputImageFormat.bgra8888 : InputImageFormat.nv21;
      final inputImageMetadata = InputImageMetadata(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        rotation: InputImageRotation.values.firstWhere(
          (element) =>
              element.rawValue == _controller!.description.sensorOrientation,
          orElse: () => InputImageRotation.rotation0deg,
        ),
        format: format,
        bytesPerRow: image.planes[0].bytesPerRow,
      );
      final bytes = _concatenatePlanes(image.planes);
      return InputImage.fromBytes(bytes: bytes, metadata: inputImageMetadata);
    } catch (e) {
      print(e);
      return null;
    }
  }

  Uint8List _concatenatePlanes(List<Plane> planes) {
    final allBytes = WriteBuffer();
    for (Plane plane in planes) {
      allBytes.putUint8List(plane.bytes);
    }
    return allBytes.done().buffer.asUint8List();
  }

  // void _toggleCamera() async {
  //   if (cameras.isEmpty || cameras.length < 2) {
  //     print("Can't toggle camera. not enough cameras available");
  //     return;
  //   }

  //   if (_controller != null && _controller!.value.isStreamingImages) {
  //     await _controller!.stopImageStream();
  //   }
  //   _selectedCameraIndex = (_selectedCameraIndex + 1) % cameras.length;
  //   setState(() {
  //     _faces = [];
  //   });
  //   await _initializeCamera(cameras[_selectedCameraIndex]);
  // }

  void _startFaceDetection() {
    if (_controller == null || !_controller!.value.isInitialized) {
      return;
    }
    _controller!.startImageStream((CameraImage image) async {
      if (_isDetecting) return;
      _isDetecting = true;

      final inputImage = _convertCameraImageToInputImage(image);

      if (inputImage == null) {
        _isDetecting = false;
        return;
      }
      try {
        final List<Face> faces = await _faceDetector.processImage(inputImage);
        final primaryFace = _selectPrimaryFace(faces);
        if (mounted) {
          setState(() {
            _faces = primaryFace == null ? [] : [primaryFace]; // <<< only 1
            if (primaryFace != null) {
              _pendingCameraImage = image;
              _pendingSize = Size(
                image.width.toDouble(),
                image.height.toDouble(),
              );
              _pendingFace = primaryFace;

              final jpgBytes = cropFaceToJpeg256(
                _pendingCameraImage!,
                _pendingFace!,
              );
              if (jpgBytes != null) {
                // Todo Call api send image
                // json = jsonFetch()
              }
            }
          });
        }
      } catch (e) {
        print(e);
      } finally {
        _isDetecting = false;
      }
    });
  }
  // //used to test if 256x256 face image frame is capture correctly
  //   Future<void> showImagePopup(BuildContext context, Uint8List jpgBytes) async {
  //     showDialog(
  //       context: context,
  //       builder: (context) {
  //         return AlertDialog(
  //           contentPadding: EdgeInsets.zero,
  //           content: Image.memory(jpgBytes),
  //         );
  //       },
  //     );
  //   }

  /// Crop detected face and export as 256x256 JPEG
  Uint8List? cropFaceToJpeg256(CameraImage cameraImage, Face face) {
    try {
      // 1️⃣ Convert CameraImage to RGB BFRA8888
      img.Image baseImage;
      if (cameraImage.format.group == ImageFormatGroup.yuv420) {
        baseImage = _convertYUV420toImageColor(cameraImage);
      } else if (cameraImage.format.group == ImageFormatGroup.bgra8888) {
        // iOS: BGRA8888 format
        final plane = cameraImage.planes[0];
        final int width = cameraImage.width;
        final int height = cameraImage.height;
        final int bytesPerRow = plane.bytesPerRow;
        final Uint8List bgraBytes = plane.bytes;

        // Create img.Image with explicit BGRA to RGBA conversion to avoid color issues
        baseImage = img.Image(width: width, height: height);
        const int bytesPerPixel = 4; // BGRA8888

        for (int y = 0; y < height; y++) {
          for (int x = 0; x < width; x++) {
            final int index = y * bytesPerRow + x * bytesPerPixel;
            if (index + 3 < bgraBytes.length) {
              final int b = bgraBytes[index]; // Blue
              final int g = bgraBytes[index + 1]; // Green
              final int r = bgraBytes[index + 2]; // Red
              final int a = bgraBytes[index + 3]; // Alpha
              // Set pixel as RGBA (image package expects RGBA)
              baseImage.setPixelRgba(x, y, r, g, b, a);
            }
          }
        }
      } else {
        throw Exception('Unsupported format: ${cameraImage.format.group}');
      }

      // 2️⃣ Get the bounding box from MLKit face detection
      final rect = face.boundingBox;

      // Ensure crop bounds are valid
      final x = rect.left.clamp(0, baseImage.width - 1).toInt();
      final y = rect.top.clamp(0, baseImage.height - 1).toInt();
      final w = rect.width.clamp(1, baseImage.width - x).toInt();
      final h = rect.height.clamp(1, baseImage.height - y).toInt();

      // 3️⃣ Crop and resize to 256x256
      final cropped = img.copyCrop(baseImage, x: x, y: y, width: w, height: h);
      final resized = img.copyResize(cropped, width: 256, height: 256);

      // 4️⃣ Encode as JPEG
      return Uint8List.fromList(img.encodeJpg(resized, quality: 90));
    } catch (e) {
      print('cropFaceToJpeg256 error: $e');
      return null;
    }
  }

  /// Helper: convert YUV420 (Android) → RGB image
  img.Image _convertYUV420toImageColor(CameraImage image) {
    final width = image.width;
    final height = image.height;
    final uvRowStride = image.planes[1].bytesPerRow;
    final uvPixelStride = image.planes[1].bytesPerPixel!;
    final imgBytes = Uint8List(width * height * 3);

    int pixelIndex = 0;
    for (int y = 0; y < height; y++) {
      final uvRow = uvRowStride * (y >> 1);
      for (int x = 0; x < width; x++) {
        final uvOffset = uvRow + (x >> 1) * uvPixelStride;
        final yp = image.planes[0].bytes[y * image.planes[0].bytesPerRow + x];
        final up = image.planes[1].bytes[uvOffset];
        final vp = image.planes[2].bytes[uvOffset];

        int r = (yp + vp * 1436 / 1024 - 179).clamp(0, 255).toInt();
        int g =
            (yp - up * 46549 / 131072 + 44 - vp * 93604 / 131072 + 91)
                .clamp(0, 255)
                .toInt();
        int b = (yp + up * 1814 / 1024 - 227).clamp(0, 255).toInt();

        imgBytes[pixelIndex++] = r;
        imgBytes[pixelIndex++] = g;
        imgBytes[pixelIndex++] = b;
      }
    }

    return img.Image.fromBytes(
      width: width,
      height: height,
      bytes: imgBytes.buffer,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text("Face Attendance App")),
      body:
          _initializeControllerFuture == null
              ? Center(child: Text("No Camera Available"))
              : FutureBuilder<void>(
                future: _initializeControllerFuture,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.done &&
                      _controller != null &&
                      _controller!.value.isInitialized) {
                    return Stack(
                      fit: StackFit.expand,
                      children: [
                        CameraPreview(_controller!),
                        CustomPaint(
                          painter: FaceDetectionPainter(
                            faces: _faces,
                            imageSize: _pendingSize ?? const Size(1, 1),
                            cameraLensDirection:
                                _controller!.description.lensDirection,
                          ),
                        ),

                        Positioned(
                          top: 20,
                          left: 0,
                          right: 0,
                          child: Center(
                            child: Container(
                              padding: EdgeInsets.symmetric(
                                vertical: 8,
                                horizontal: 16,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.black,
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Text(
                                'Name: ${_faces.length}',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ),
                        ),

                        Positioned(
                          top: 20,
                          right: 0,
                          child: Center(
                            child: Container(
                              padding: EdgeInsets.symmetric(
                                vertical: 8,
                                horizontal: 16,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.black,
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: ValueListenableBuilder<DateTime>(
                                valueListenable: _now,
                                builder:
                                    (_, now, __) => Text(
                                      'Time: ${_fmt(now)}',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    );
                  } else if (snapshot.hasError) {
                    return Center(child: Text('Error'));
                  } else {
                    return Center(
                      child: CircularProgressIndicator(
                        color: Colors.blueAccent,
                      ),
                    );
                  }
                },
              ),
    );
  }
}
