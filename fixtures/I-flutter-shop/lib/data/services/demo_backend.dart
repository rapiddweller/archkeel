import 'package:shop/domain/catalog/product.dart';
import 'package:shop/domain/checkout/shop_status.dart';
import 'package:shop/domain/orders/order.dart';

class DemoBackend implements ShopStatus {
  bool _isOnline = true;
  bool _failNextRequest = false;

  @override
  bool isOnline() => _isOnline;

  @override
  void setOnline(bool online) => _isOnline = online;

  void failNextRequest() => _failNextRequest = true;

  Future<List<Product>> fetchCatalog() async {
    await Future<void>.value();
    _checkRequest();
    return const [
      Product('trail-mix', 'Trail Mix', 399),
      Product('oat-bar', 'Oat Bar', 149),
      Product('apple', 'Apple', 99),
    ];
  }

  Future<Order> submitOrder(Order order) async {
    await Future<void>.value();
    _checkRequest();
    return order;
  }

  Future<List<Order>> fetchOrders() async {
    await Future<void>.value();
    _checkRequest();
    return const [];
  }

  void _checkRequest() {
    if (!_isOnline) throw StateError('Offline');
    if (_failNextRequest) {
      _failNextRequest = false;
      throw StateError('Temporary backend failure');
    }
  }
}
