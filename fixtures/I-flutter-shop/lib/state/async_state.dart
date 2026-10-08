enum LoadPhase { idle, loading, empty, ready, failed }

class AsyncState<T> {
  const AsyncState(this.phase, this.value, this.error);

  final LoadPhase phase;
  final T? value;
  final Object? error;
}
