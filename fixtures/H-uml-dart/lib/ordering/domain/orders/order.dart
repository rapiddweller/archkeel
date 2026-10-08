typedef OrderId = String;
const int CURRENCY_SCALE = 100;

enum OrderStatus { draft, placed, cancelled }

class OrderLine {
  const OrderLine(String this.sku, int this.quantity, int this.unitPriceCents);

  final String sku;
  final int quantity;
  final int unitPriceCents;

  int totalCents() => quantity * unitPriceCents;
}

class Order {
  Order(String this.id, {List<OrderLine> lines = const []})
    : _lines = List.of(lines);

  static const int maxLines = 20;

  final String id;
  final List<OrderLine> _lines;
  OrderStatus status = OrderStatus.draft;

  static bool isValidQuantity(int quantity) => quantity > 0;

  void addLine(OrderLine line) {
    if (status != OrderStatus.draft ||
        !isValidQuantity(line.quantity) ||
        _lines.length >= maxLines) {
      throw StateError('line cannot be added');
    }
    _lines.add(line);
  }

  void place() {
    if (status != OrderStatus.draft || _lines.isEmpty) {
      throw StateError('order cannot be placed');
    }
    status = OrderStatus.placed;
  }

  int total() => _lines.fold(0, (sum, line) => sum + line.totalCents());
}
