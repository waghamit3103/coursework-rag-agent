# Linear Regression

Linear regression models the relationship between a dependent variable y and
one or more independent variables X as a linear function:
y = w^T x + b, where w is a weight vector and b is a bias term. The goal of
training is to find the w and b that minimize a loss function over the
training data — almost always mean squared error (MSE) for linear
regression, since it has a convenient closed-form solution and a nicely
convex loss surface.

## The normal equation

For MSE loss, the optimal weights have a closed-form solution:

w = (X^T X)^(-1) X^T y

This is exact — no iteration required — but it requires inverting the
(d x d) matrix X^T X, which is O(d^3) and becomes impractical once the
number of features d gets large (roughly d > 10,000 in practice), and it
fails outright if X^T X is singular (which happens when features are
perfectly collinear, or when there are more features than examples). For
those cases, gradient descent is used instead.

## Gradient descent

Gradient descent updates the weights iteratively in the direction that
reduces the loss fastest:

w := w - alpha * gradient(Loss, w)

where alpha is the learning rate. Too large a learning rate causes the
updates to overshoot the minimum and diverge; too small a learning rate
converges reliably but very slowly. In practice, a learning rate schedule
(starting larger and decaying over training) or an adaptive optimizer like
Adam handles this trade-off much better than a single fixed learning rate.

Batch gradient descent computes the gradient over the entire training set
per update (accurate but slow per step, and memory-heavy for large
datasets); stochastic gradient descent (SGD) computes the gradient from a
single example per update (noisy but fast, and the noise itself can help
escape shallow local minima in non-convex problems); mini-batch gradient
descent — computing the gradient over a small batch, typically 32 to 256
examples — is the standard middle ground used in practice, balancing update
stability against per-step compute cost.

## Regularization

Plain linear regression can overfit when there are many features relative
to the number of training examples, especially with correlated features.
Two standard fixes:

**Ridge regression (L2 regularization)** adds a penalty term
lambda * ||w||^2 to the loss. This shrinks all weights toward zero (but
not exactly to zero), which reduces variance at the cost of a small amount
of bias — a favorable trade-off whenever the unregularized model is
overfitting. Ridge has a closed-form solution just like plain linear
regression, since the added penalty term is still differentiable and convex.

**Lasso regression (L1 regularization)** adds a penalty term
lambda * ||w||_1 instead. Unlike L2, the L1 penalty tends to push some
weights to exactly zero, which performs implicit feature selection — useful
when you suspect many features are irrelevant and want a sparse, more
interpretable model. Lasso does not have a closed-form solution (the L1
penalty isn't differentiable at zero), so it requires an iterative
optimization method such as coordinate descent.

Elastic Net combines both penalties, getting some of Lasso's sparsity along
with some of Ridge's stability when features are highly correlated (Lasso
alone tends to arbitrarily pick just one feature out of a correlated group
and zero out the rest, which can be undesirable).

## Assumptions and diagnostics

Linear regression's standard error estimates and hypothesis tests rely on
several assumptions: linearity of the relationship between X and y,
independence of errors, homoscedasticity (constant variance of errors across
all values of X), and normally distributed errors. Violating linearity
usually shows up as a clear pattern in a residual plot (residuals vs.
predicted values) rather than random scatter; violating homoscedasticity
shows up as a "funnel" shape in that same plot, where residual spread grows
or shrinks systematically with the predicted value.
