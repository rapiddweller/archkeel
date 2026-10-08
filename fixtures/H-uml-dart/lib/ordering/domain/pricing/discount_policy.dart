const int MAX_DISCOUNT_PERCENT = 50;

abstract interface class DiscountPolicy {
  int discountCents(int subtotalCents);
}

class DiscountBase {
  int clampDiscount(int subtotalCents, int requestedCents) =>
      requestedCents.clamp(0, subtotalCents);
}

class PercentageDiscount extends DiscountBase implements DiscountPolicy {
  PercentageDiscount({int percent = 0}) : _percent = percent;

  final int _percent;

  @override
  int discountCents(int subtotalCents) => super.clampDiscount(
    subtotalCents,
    subtotalCents * _percent.clamp(0, MAX_DISCOUNT_PERCENT) ~/ 100,
  );
}
