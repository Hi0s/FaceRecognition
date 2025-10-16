import 'dart:io';

import 'package:http/http.dart';

class ApiService {
  String path = "";
  var uploadUri;
  var getResultUri;

  ApiService() {
    if (Platform.isIOS) {
      path = "https://jsonplaceholder.typicode.com/";
    }
    uploadUri = Uri.parse('$path/api/');
  }
}
