# -*- coding: utf-8 -*-
"""
Created on Tue Jun 29 17:17:19 2021

@author: amber
"""
import sys
import os
import argparse

import numpy as np
from scipy.sparse import lil_matrix
import pickle
import random
import torch
import torch.nn.functional as F
import pyhocon
import dgl

from scipy import sparse
from dgl.nn.pytorch import GraphConv as GraphConv

from src.dataCenter import *
from src.utils import *
from src.models import *
import src.plotter as plotter
import src.graph_statistics as GS
import src.compare_gsageKdd_helper as helper
from src import classification


#%%  arg setup
parser = argparse.ArgumentParser(description='pytorch version of GraphSAGE')

parser.add_argument('--dataSet', type=str, default='ACM')
parser.add_argument('--agg_func', type=str, default='MAX')
parser.add_argument('--epochs', type=int, default=1)
parser.add_argument('--b_sz', type=int, default=400)
parser.add_argument('--seed', type=int, default=123)
parser.add_argument('--cuda', action='store_true',
					help='use CUDA')
parser.add_argument('--gcn', action='store_true')
parser.add_argument('--learn_method', type=str, default='unsup')
parser.add_argument('--unsup_loss', type=str, default='normal')
parser.add_argument('--max_vali_f1', type=float, default=0)
parser.add_argument('--name', type=str, default='debug')
parser.add_argument('--config', type=str, default='./src/experiments.conf')

args_graphsage = parser.parse_args()


parser = argparse.ArgumentParser(description='Inductive Interface')

parser.add_argument('--model', type=str, default='KDD')
parser.add_argument('--dataSet', type=str, default='ACM')
parser.add_argument('--seed', type=int, default=123)
parser.add_argument('-num_node', dest="num_node", default=-1, type=str,
                    help="the size of subgraph which is sampled; -1 means use the whule graph")
parser.add_argument('--config', type=str, default='/Users/parmis/Desktop/parmis-thesis/related-work/codes/graphSAGE-pytorch-master/src/experiments.conf')
parser.add_argument('-decoder_type', dest="decoder_type", default="multi_inner_product",
                    help="the decoder type, Either SBM or InnerDot  or TransE or MapedInnerProduct_SBM or multi_inner_product and TransX or SBM_REL")
parser.add_argument('-encoder_type', dest="encoder_type", default="Multi_GCN",
                    help="the encoder type, Either ,mixture_of_GCNs, mixture_of_GatedGCNs , Multi_GCN or Edge_GCN ")
parser.add_argument('-f', dest="use_feature", default=True, help="either use features or identity matrix")
parser.add_argument('-NofRels', dest="num_of_relations", default=2,
                    help="Number of latent or known relation; number of deltas in SBM")
parser.add_argument('-NofCom', dest="num_of_comunities", default=128,
                    help="Number of comunites, tor latent space dimention; len(z)")
parser.add_argument('-BN', dest="batch_norm", default=True,
                    help="either use batch norm at decoder; only apply in multi relational decoders")
parser.add_argument('-DR', dest="DropOut_rate", default=.3, help="drop out rate")
parser.add_argument('-encoder_layers', dest="encoder_layers", default="64", type=str,
                    help="a list in which each element determine the size of gcn; Note: the last layer size is determine with -NofCom")
parser.add_argument('-lr', dest="lr", default=0.005, help="model learning rate")
parser.add_argument('-e', dest="epoch_number", default=2, help="Number of Epochs")
parser.add_argument('-NSR', dest="negative_sampling_rate", default=1,
                    help="the rate of negative samples which should be used in each epoch; by default negative sampling wont use")
parser.add_argument('-v', dest="Vis_step", default=50, help="model learning rate")
parser.add_argument('-modelpath', dest="mpath", default="VGAE_FrameWork_MODEL", type=str,
                    help="The pass to save the learned model")
parser.add_argument('-Split', dest="split_the_data_to_train_test", default=True,
                    help="either use features or identity matrix; for synthasis data default is False")
parser.add_argument('-s', dest="save_embeddings_to_file", default=True, help="save the latent vector of nodes")

args_kdd = parser.parse_args()
pltr = plotter.Plotter(functions=["Accuracy", "loss", "AUC"])

if torch.cuda.is_available():
	if not args.cuda:
		print("WARNING: You have a CUDA device, so you should probably run with --cuda")
	else:
		device_id = torch.cuda.current_device()
		print('using device', device_id, torch.cuda.get_device_name(device_id))

device = torch.device("cpu")
# print('DEVICE:', device)


#%% load config

random.seed(args_graphsage.seed)
np.random.seed(args_graphsage.seed)
torch.manual_seed(args_graphsage.seed)
torch.cuda.manual_seed_all(args_graphsage.seed)

# load config file
config = pyhocon.ConfigFactory.parse_file(args_graphsage.config)

#%% load data
ds = args_graphsage.dataSet
if ds == 'cora':
    dataCenter_sage = DataCenter(config)
    dataCenter_sage.load_dataSet(ds, "graphSage")
    features_sage = torch.FloatTensor(getattr(dataCenter_sage, ds+'_feats')).to(device)
    
    dataCenter_kdd = DataCenter(config)
    dataCenter_kdd.load_dataSet(ds, "KDD")
    features_kdd = torch.FloatTensor(getattr(dataCenter_kdd, ds+'_feats')).to(device)
elif ds == 'IMDB' or ds == 'ACM':
    dataCenter_kdd = DataCenter(config)
    dataCenter_kdd.load_dataSet(ds, "KDD")
    features_kdd = torch.FloatTensor(getattr(dataCenter_kdd, ds+'_feats')).to(device)

    dataCenter_sage = datasetConvert(dataCenter_kdd, ds)
    features_sage = features_kdd


#%% train graphSAGE and KDD model

# train graphsage
from src.models import *
graphSage, classification_sage = helper.train_graphSage(dataCenter_sage, 
                                        features_sage,args_graphsage,
                                        config, device)

#%%  train inductive_kdd
inductive_kdd = helper.train_kddModel(dataCenter_kdd, features_kdd, 
                                      args_kdd, device)



#%% get embedding of GraphSAGE
embedding_sage = get_gnn_embeddings(graphSage, dataCenter_sage, ds)

#%% get embedding of KDD
graph_dgl = dgl.from_scipy(sparse.csr_matrix(getattr(dataCenter_kdd, ds+'_adj_lists')))
graph_dgl.add_edges(graph_dgl.nodes(), graph_dgl.nodes())  # the library does not add self-loops  
std_z, m_z, z, reconstructed_adj = inductive_kdd(graph_dgl, features_kdd)
embedding_kdd = z.detach().numpy()

#%% train classification/prediction model - NN
trainId = getattr(dataCenter_kdd, ds + '_train')
labels = getattr(dataCenter_kdd, ds + '_labels')
res_train_sage, classifier_sage = classification.NN_all(embedding_sage[trainId, :], 
                                                             labels[trainId])
res_train_kdd, classifier_kdd = classification.NN_all(embedding_kdd[trainId, :], 
                                                           labels[trainId])

#%% evaluate on whole dataset


# ********************** TRAIN SET
print('\n# ****************** TRAIN SET ******************')
print('#  GraphSAGE')
print(res_train_sage[-1])
print('#  KDD Model')
print(res_train_kdd[-1])


labels_pred_sage = classifier_sage.predict(torch.Tensor(embedding_sage))
labels_pred_kdd = classifier_kdd.predict(torch.Tensor(embedding_kdd))

# ********************** TEST SET
print('\n# ****************** TEST SET ******************')
testId = [i for i in range(len(labels)) if i not in trainId]
print('#  GraphSAGE')
helper.print_eval(labels[testId], labels_pred_sage[testId])
print('#  KDD Model')
helper.print_eval(labels[testId], labels_pred_kdd[testId])

# ********************** WHOLE SET
print('\n# ****************** WHOLE SET ******************')
print('#  GraphSAGE')
helper.print_eval(labels, labels_pred_sage)
print('#  KDD Model')
helper.print_eval(labels, labels_pred_kdd)


