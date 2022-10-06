from typing import NamedTuple, Optional
import torch

from fab.types_ import LogProbFunc


class Point:
    """Keeps important info on points in the AIS chain. Saves us having to re-evaluate the target
    and base log prob/ score functions."""
    def __init__(self,
        x: torch.Tensor,
        log_q: torch.Tensor,
        log_p: torch.Tensor,
        grad_log_q: Optional[torch.Tensor] = None,
        grad_log_p: Optional[torch.Tensor] = None):
        self.x = x
        self.log_q = log_q
        self.log_p = log_p
        self.grad_log_q = grad_log_q
        self.grad_log_p = grad_log_p

    @property
    def device(self):
        return self.x.device

    def to(self, device):
        self.x = self.x.to(device)
        self.log_q = self.log_q.to(device)
        self.log_p = self.log_p.to(device)
        self.grad_log_q = self.grad_log_q.to(device) if self.grad_log_q is not None else None
        self.grad_log_p = self.grad_log_p.to(device) if self.grad_log_p is not None else None

    def __getitem__(self, indices):
        log_p = self.log_p[indices]
        grad_log_q = self.grad_log_q[indices] if self.grad_log_q is not None else None
        grad_log_p = self.grad_log_p[indices] if self.grad_log_p is not None else None
        return Point(self.x[indices],
                     self.log_q[indices],
                     log_p, grad_log_q, grad_log_p)

    def __setitem__(self, indices, values):
        self.x[indices] = values.x
        self.log_q[indices] = values.log_q
        self.log_p[indices] = values.log_p
        if self.grad_log_q is not None:
            self.grad_log_q[indices] = values.grad_log_q
            self.grad_log_p[indices] = values.grad_log_p


def grad_and_value(x, forward_fn):
    """Calculate the forward pass of a function y = f(x) as well as its gradient w.r.t x."""
    x = x.detach()
    x.requires_grad = True
    y = forward_fn(x)
    grad = torch.autograd.grad(y, x,  grad_outputs=torch.ones_like(y))[0]
    return grad.detach(), y.detach()


def create_point(x: torch.Tensor, log_q_fn: LogProbFunc, log_p_fn: LogProbFunc,
                 with_grad: bool, log_q_x: Optional[torch.Tensor] = None) -> Point:
    """Create an instance of a `Point` which contains the necessary info on a point for MCMC.
    If this is at the start of an AIS chain, we may already have access to log_q_x, which may then
     be used rather than recalculating log_q_x using the log_q_fn. """
    if with_grad:
        grad_log_q, log_q = grad_and_value(x, log_q_fn)
        grad_log_p, log_p = grad_and_value(x, log_p_fn)
        return Point(x=x, log_p=log_p, log_q=log_q, grad_log_p=grad_log_p, grad_log_q=grad_log_q)
    else:
        # Use log_q_x if we already have it, otherwise calculate it.
        log_q_x = log_q_x if log_q_x else log_q_fn(x)
        return Point(x=x, log_q=log_q_x, log_p=log_p_fn(x))


def get_intermediate_log_prob(x: Point,
                              beta: float,
                              p_sq_over_q_target: bool) -> torch.Tensor:
    """Get log prob of point according to intermediate AIS distribution.
    Set AIS final target g=p^2/q if p_sq_over_q_target else g=p.
    log_prob = (1 - beta) log_q + beta log_g
    """
    if p_sq_over_q_target:
        return (1 - 2*beta) * x.log_q + 2*beta*x.log_p
    else:
        return (1-beta) * x.log_q + beta * x.log_p


def get_grad_intermediate_log_prob(
        x: Point,
        beta: float,
        p_sq_over_q_target: bool) -> torch.Tensor:
    """Get gradient of intermediate AIS distribution for a point.
    Set AIS final target g=p^2/q if p_sq_over_q_target else g=p.
    \nabla_x log_prob = (1 - beta) \nabla_x log_q + beta \nabla_x log_g
    """
    if p_sq_over_q_target:
        return (1 - 2*beta) * x.grad_log_q + 2*beta*x.grad_log_p
    else:
        return (1-beta) * x.grad_log_q + beta * x.grad_log_p

