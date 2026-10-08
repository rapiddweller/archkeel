import '../ordering/application/checkout_service.dart';
import '../ordering/domain/orders/order.dart';

class CheckoutRequest {
  const CheckoutRequest(String this.requestId, List<OrderLine> this.lines);

  final String requestId;
  final List<OrderLine> lines;
}

class CheckoutController {
  CheckoutController(CheckoutService checkout) : _checkout = checkout;

  final CheckoutService _checkout;

  String submit(CheckoutRequest request) {
    final order = Order(_requestId(request), lines: request.lines);
    return _checkout.checkout(order);
  }

  String _requestId(CheckoutRequest request) => request.requestId;
}
