// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import 'package:flutter/material.dart';
import 'package:shop/data/http_order_repository.dart';

// The order screen loads after the first frame, so its library is deferred.
import 'presentation/order_page.dart' deferred as order_page;

Future<void> main() async {
  await order_page.loadLibrary();
  runApp(
    MaterialApp(
      home: order_page.OrderPage(repository: HttpOrderRepository.remote()),
    ),
  );
}
