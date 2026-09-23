// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shop/domain/domain.dart' show Order, OrderLine;
import 'package:shop/domain/repository.dart' show OrderRepository;

// A browser build has no dart:io, so the client comes from whichever library the platform has.
import 'client_stub.dart' if (dart.library.io) 'client_io.dart';

class HttpOrderRepository implements OrderRepository {
  HttpOrderRepository(this._client, this._base);

  factory HttpOrderRepository.remote() =>
      HttpOrderRepository(createClient(), Uri.parse('https://shop.example/api/'));

  final http.Client _client;
  final Uri _base;

  @override
  Future<List<Order>> ordersOf(String customerId) async {
    final response = await _client.get(_base.resolve('customers/$customerId/orders'));
    final items = (jsonDecode(response.body) as List<dynamic>).cast<Map<String, dynamic>>();
    return [for (final item in items) _order(item)];
  }

  @override
  Future<void> save(Order order) async {
    await _client.put(_base.resolve('orders/${order.id}'), body: jsonEncode({'id': order.id}));
  }

  Order _order(Map<String, dynamic> item) => Order(item['id'] as String, [
        for (final line in (item['lines'] as List<dynamic>).cast<Map<String, dynamic>>())
          OrderLine(
            line['description'] as String,
            line['quantity'] as int,
            line['unit_cents'] as int,
          ),
      ]);
}
