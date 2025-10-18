import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class ApiService {
  final storage = FlutterSecureStorage();
  String url = "";
  var uploadUri;
  var getResultUri;

  ApiService() {
    // if (Platform.isIOS) {
    url = "http://192.168.0.174:8000";
    // }
    uploadUri = Uri.parse('$url/api/face-match/');
    // getResultUri = Uri.parse('$url/api/getResult');
  }

  upload(Uint8List img) async {
    try {
      var request = http.MultipartRequest('POST', uploadUri);
      request.files.add(
        http.MultipartFile.fromBytes('image', img, filename: 'upload.jpg'),
      );

      var response = await request.send();
      final respStr = await response.stream.bytesToString();
      print('Response status: ${response.statusCode}');
      print('Response body: $respStr');
      return response;
    } catch (e) {
      return 0;
    }
  }
}
