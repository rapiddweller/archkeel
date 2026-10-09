// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

/// The screen listing one customer's orders.
library;

import 'package:flutter/material.dart';
import 'package:shop/domain/domain.dart';

import 'order_tile.dart';

part 'order_page_state.dart';

class OrderPage extends StatefulWidget {
  const OrderPage({Key? key, required this.repository}) : super(key: key);

  final OrderRepository repository;

  @override
  State<OrderPage> createState() => _OrderPageState();
}
