import numpy as np
import torch
import normflows as nf
import larsflow as lf
from fab.wrappers.normflows import WrappedNormFlowModel
from fab.trainable_distributions import TrainableDistribution


def make_normflow_flow(dim: int,
                       n_flow_layers: int,
                       layer_nodes_per_dim: int,
                       act_norm: bool):
    # Define list of flows
    flows = []
    layer_width = dim * layer_nodes_per_dim
    for i in range(n_flow_layers):
        # Neural network with two hidden layers having 32 units each
        # Last layer is initialized by zeros making training more stable
        param_map = nf.nets.MLP([int((dim / 2) + 0.5), layer_width, layer_width, dim], init_zeros=True)
        # Add flow layer
        flows.append(nf.flows.AffineCouplingBlock(param_map, scale_map="exp"))
        # Swap dimensions
        flows.append(nf.flows.InvertibleAffine(dim))
        # ActNorm
        if act_norm:
            flows.append(nf.flows.ActNorm(dim))
    return flows


def make_normflow_snf(base: nf.distributions.BaseDistribution,
                      target: nf.distributions.Target,
                      dim: int,
                      n_flow_layers: int,
                      layer_nodes_per_dim: int,
                      act_norm: bool,
                      it_snf_layer: int = 2,
                      mh_prop_scale: float = 0.1,
                      mh_steps: int = 10):
    # Define list of flows
    flows = []
    layer_width = dim * layer_nodes_per_dim
    for i in range(n_flow_layers):
        # Neural network with two hidden layers having 32 units each
        # Last layer is initialized by zeros making training more stable
        param_map = nf.nets.MLP([int((dim / 2) + 0.5), layer_width, layer_width, dim], init_zeros=True)
        # Add flow layer
        flows.append(nf.flows.AffineCouplingBlock(param_map, scale_map="exp"))
        # Swap dimensions
        flows.append(nf.flows.InvertibleAffine(dim))
        # ActNorm
        if act_norm:
            flows.append(nf.flows.ActNorm(dim))
        # Sampling layer of SNF
        if (i + 1) % it_snf_layer == 0:
            prop_scale = mh_prop_scale * np.ones(dim)
            proposal = nf.distributions.DiagGaussianProposal((dim,), prop_scale)
            lam = (i + 1) / n_flow_layers
            dist = nf.distributions.LinearInterpolation(target, base, lam)
            flows.append(nf.flows.MetropolisHastings(dist, proposal, mh_steps))

    return flows


def make_wrapped_normflow_realnvp(
        dim: int,
        n_flow_layers: int = 5,
        layer_nodes_per_dim: int = 10,
        act_norm: bool = True) -> TrainableDistribution:
    """Created a wrapped normflows distribution using the example from the normflows page."""
    base = nf.distributions.base.DiagGaussian(dim)
    flows = make_normflow_flow(dim, n_flow_layers=n_flow_layers,
                               layer_nodes_per_dim=layer_nodes_per_dim,
                               act_norm=act_norm)
    model = nf.NormalizingFlow(base, flows)
    wrapped_dist = WrappedNormFlowModel(model)
    if act_norm:
        wrapped_dist.sample((500,))  # ensure we call sample to initialise the ActNorm layers
    return wrapped_dist


def make_normflow_snf_model(
        dim: int,
        target: nf.distributions.Target,
        n_flow_layers: int = 5,
        layer_nodes_per_dim: int = 10,
        act_norm: bool = True,
        it_snf_layer: int = 2,
        mh_prop_scale: float = 0.1,
        mh_steps: int = 10) \
        -> nf.NormalizingFlow:
    """Created normflows distribution with sampling layers."""
    base = nf.distributions.base.DiagGaussian(dim)
    flows = make_normflow_snf(base,
                              target,
                              dim,
                              n_flow_layers=n_flow_layers,
                              layer_nodes_per_dim=layer_nodes_per_dim,
                              act_norm=act_norm,
                              it_snf_layer=it_snf_layer,
                              mh_prop_scale=mh_prop_scale,
                              mh_steps=mh_steps)
    model = nf.NormalizingFlow(base, flows, p=target)
    if act_norm:
        model.sample(500)  # ensure we call sample to initialise the ActNorm layers
    return model


def make_wrapped_normflow_resampled_flow(
        dim: int,
        n_flow_layers: int = 5,
        layer_nodes_per_dim: int = 10,
        act_norm: bool = True,
        a_hidden_layer: int = 2,
        a_hidden_units: int = 256,
        T: int = 20,
        eps: float = 0.05) \
        -> TrainableDistribution:
    """Created normflows distribution with resampled base."""
    #hu = [dim] + [a_hidden_units] * a_hidden_layer + [1]
    #a = nf.nets.MLP(hu, output_fn="sigmoid")
    resnet = nf.nets.ResidualNet(dim, 1, a_hidden_units, num_blocks=a_hidden_layer)
    a = torch.nn.Sequential(resnet, torch.nn.Sigmoid())
    base = lf.distributions.ResampledGaussian(dim, a, T, eps, trainable=False)
    flows = make_normflow_flow(dim,
                               n_flow_layers=n_flow_layers,
                               layer_nodes_per_dim=layer_nodes_per_dim,
                               act_norm=act_norm)
    model = nf.NormalizingFlow(base, flows)
    if act_norm:
        model.sample(500)  # ensure we call sample to initialise the ActNorm layers
    wrapped_dist = WrappedNormFlowModel(model)
    return wrapped_dist


