import 'package:shop/domain/cart/cart.dart';

enum OrderStatus {
  placed('Placed'),
  completed('Completed');

  const OrderStatus(this.label);

  final String label;
}

class OrderLine {
  const OrderLine(
    this.productId,
    this.name,
    this.unitPriceCents,
    this.quantity,
  );

  final String productId;
  final String name;
  final int unitPriceCents;
  final int quantity;

  int get lineTotalCents => quantity * unitPriceCents;
}

class Order {
  const Order(this.id, this.lines, this.totalCents, this.status);

  factory Order.fromCart(Cart cart, String id) => Order(
    id,
    List.unmodifiable(
      cart.lines.map(
        (line) => OrderLine(
          line.product.id,
          line.product.name,
          line.product.priceCents,
          line.quantity,
        ),
      ),
    ),
    cart.totalCents,
    OrderStatus.placed,
  );

  final String id;
  final List<OrderLine> lines;
  final int totalCents;
  final OrderStatus status;
}
