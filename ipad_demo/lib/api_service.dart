import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ApiService {
  String url = "";
  var uploadUri;
  var getResultUri;

  ApiService() {
    // if (Platform.isIOS) {
    url = "http://172.20.10.13:8000";
    // }
    uploadUri = Uri.parse('$url/api/face-match/');
    // getResultUri = Uri.parse('$url/api/getResult');
  }

  Future<Map<String, dynamic>?> upload(Uint8List img) async {
    try {
      var request = http.MultipartRequest('POST', uploadUri);
      request.files.add(
        http.MultipartFile.fromBytes('image', img, filename: 'upload.jpg'),
      );

      var response = await request.send();
      final respStr = await response.stream.bytesToString();
      print('Response status: ${response.statusCode}');
      print('Response body: $respStr');
      if (response.statusCode >= 200 && response.statusCode < 300) {
        try {
          final decoded = jsonDecode(respStr) as Map<String, dynamic>;
          return decoded;
        } catch (e) {
          if (kDebugMode) {
            print('Failed to decode response json: $e');
          }
          return null;
        }
      }
      return null;
    } catch (e) {
      print('Error uploading image: $e');
      return null;
    }
  }
}
