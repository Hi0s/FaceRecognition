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
    if (Platform.isIOS) {
      url = "https://jsonplaceholder.typicode.com/";
    }
    uploadUri = Uri.parse('$url/api/uploadImage');
    getResultUri = Uri.parse('$url/api/getResult');
  }

  Upload(Uint8List img) async {
    try {
      var token = await storage.read(key: 'token');
      var request = new http.MultipartRequest('POST', uploadUri);
      Map<String, String> headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Token $token',
      };
      request.headers.addAll(headers);
      request.files.add(await http.MultipartFile.fromBytes("face image", img));

      var response = await request.send();
      final respStr = await response.stream.bytesToString();
      return response;
    } catch (e) {
      return 0;
    }
  }
}
