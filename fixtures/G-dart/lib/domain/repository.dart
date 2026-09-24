// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import 'dart:async';

import 'entities.dart';

abstract interface class OrderRepository {
  Future<List<Order>> ordersOf(String customerId);

  FutureOr<void> save(Order order);
}
