import 'package:shop/domain/cart/cart.dart';
import 'package:shop/domain/checkout/shop_status.dart';
import 'package:shop/domain/orders/order.dart';
import 'package:shop/domain/orders/order_repository.dart';

class PlaceOrder {
  PlaceOrder(this._status, this._repository);

  final ShopStatus _status;
  final OrderRepository _repository;
  int _nextOrderNumber = 1;

  Future<Order> call(Cart cart) async {
    if (!_status.isOnline())
      throw StateError('Checkout requires an online connection');
    final order = Order.fromCart(cart, 'order-$_nextOrderNumber');
    final placed = await _repository.place(order);
    _nextOrderNumber++;
    return placed;
  }
}
