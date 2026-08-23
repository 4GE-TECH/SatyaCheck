# When to Mock

Mock at **system boundaries** only: external APIs (payment, email), time and randomness, the file system (sometimes), databases (sometimes - prefer a test DB).

Never mock your own classes and modules, internal collaborators, or anything you control.

## Designing for mockability

**Inject dependencies** instead of constructing them internally:

```typescript
// Easy to mock
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to mock
function processPayment(order) {
  return new StripeClient(process.env.STRIPE_KEY).charge(order.total);
}
```

**Prefer SDK-style interfaces over a generic fetcher** - one function per external operation, so each mock returns one shape, test setup needs no conditional logic, and a test's endpoints are visible at a glance:

```typescript
// GOOD: each function is independently mockable
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch("/orders", { method: "POST", body: data }),
};

// BAD: mocking requires branching inside the mock
const api = { fetch: (endpoint, options) => fetch(endpoint, options) };
```
