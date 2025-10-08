import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';

class FaceDetectionPainter extends CustomPainter {
  final List<Face> faces;
  final Size imageSize;
  final CameraLensDirection cameraLensDirection;

  FaceDetectionPainter({
    super.repaint,
    required this.faces,
    required this.imageSize,
    required this.cameraLensDirection,
  });
  @override
  void paint(Canvas canvas, Size size) {
    final double scaleX = size.width / imageSize.width;
    final double scaleY = size.height / imageSize.height;

    final Paint facePaint =
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3.0
          ..color = Colors.green;
    final Paint landmarkPaint =
        Paint()
          ..style = PaintingStyle.fill
          ..strokeWidth = 3.0
          ..color = Colors.green;
    final Paint textBackgroundPaint =
        Paint()
          ..style = PaintingStyle.fill
          ..strokeWidth = 3.0
          ..color = Colors.black54;

    for (var i = 0; i < faces.length; i++) {
      final Face face = faces[i];

      double leftOffset = face.boundingBox.left;
      // double translateX(double x) {
      //   return cameraLensDirection == CameraLensDirection.front
      //       ? imageSize.width - x
      //       : x;
      // }

      if (cameraLensDirection == CameraLensDirection.front) {
        // leftOffset = imageSize.width - face.boundingBox.right;
        leftOffset = face.boundingBox.left;
      }

      final double left = leftOffset * scaleX;
      final double top = face.boundingBox.top * scaleY;
      final double right = leftOffset + face.boundingBox.width * scaleX;
      final double bottom =
          (face.boundingBox.top + face.boundingBox.height) * scaleY;

      canvas.drawRect(Rect.fromLTRB(left, top, right, bottom), facePaint);
      void drawLandmark(FaceLandmarkType type) {
        if (face.landmarks[type] != null) {
          final point = face.landmarks[type]!.position;
          double pointX = point.x.toDouble();
          if (cameraLensDirection == CameraLensDirection.front) {
            pointX = imageSize.width;
          }
          canvas.drawCircle(
            Offset(pointX * scaleX, point.y * scaleY),
            4.0,
            landmarkPaint,
          );
        }
      }

      drawLandmark(FaceLandmarkType.leftEye);
      drawLandmark(FaceLandmarkType.rightEye);
      drawLandmark(FaceLandmarkType.noseBase);
      drawLandmark(FaceLandmarkType.leftMouth);
      drawLandmark(FaceLandmarkType.rightMouth);
      drawLandmark(FaceLandmarkType.bottomMouth);

      String mood = 'Neutral';
      final smileProb = face.smilingProbability ?? 0;
      if (smileProb > 0.8) {
        mood = 'Laughing 😂';
      } else if (smileProb > 0.5) {
        mood = 'Smiling 😊';
      } else if (smileProb < 0.1) {
        mood = 'Serious 🙄';
      }

      final TextSpan faceIdSpan = TextSpan(
        text: 'Face ${i + 1}\n$mood',
        style: TextStyle(
          color: Colors.white,
          fontSize: 14,
          fontWeight: FontWeight.bold,
        ),
      );

      final TextPainter textPainter = TextPainter(
        text: faceIdSpan,
        textDirection: TextDirection.ltr,
        textAlign: TextAlign.center,
      );
      textPainter.layout();

      final textRect = Rect.fromLTWH(
        left,
        top - textPainter.height - 8,
        textPainter.width + 16,
        textPainter.height + 8,
      );
      canvas.drawRRect(
        RRect.fromRectAndRadius(textRect, Radius.circular(10)),
        textBackgroundPaint,
      );
      textPainter.paint(canvas, Offset(left + 8, top - textPainter.height - 4));
    }
  }

  @override
  bool shouldRepaint(FaceDetectionPainter oldDelegate) {
    return oldDelegate.faces != faces;
  }
}
