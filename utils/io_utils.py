import os

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import torch
import networkx as nx
import tensorboardX

def gen_prefix(args):
    if args.bmname is not None:
        name = args.bmname
    else:
        name = args.dataset
    name += '_' + args.method

    name += '_h' + str(args.hidden_dim) + '_o' + str(args.output_dim)
    if not args.bias:
        name += '_nobias'
    if len(args.name_suffix) > 0:
        name += '_' + args.name_suffix
    return name

def gen_explainer_prefix(args):
    name = gen_prefix(args) + '_explain'
    return name

def create_filename(save_dir, args, isbest=False, num_epochs=-1):
    '''
    Args:
        args: the arguments parsed in the parser
        isbest: whether the saved model is the best-performing one
        num_epochs: epoch number of the model (when isbest=False)
    '''
    filename = os.path.join(save_dir, gen_prefix(args))
    os.makedirs(filename, exist_ok=True)

    if isbest:
        filename = os.path.join(filename, 'best')
    elif num_epochs > 0:
        filename = os.path.join(filename, str(num_epochs))

    return filename + '.pth.tar'

def save_checkpoint(model, optimizer, args, num_epochs=-1, isbest=False, cg_dict=None):
    filename = create_filename(args.ckptdir, args, isbest, num_epochs=num_epochs)
    torch.save({'epoch': num_epochs,
                'model_type': args.method,
                'optimizer': optimizer,
                'model_state': model.state_dict(),
                'optimizer_state': optimizer.state_dict(),
                'cg': cg_dict},
               filename)

def load_ckpt(args, isbest=False):
    print('loading model')
    filename = create_filename(args.ckptdir, args, isbest)
    if os.path.isfile(filename):
        print("=> loading checkpoint '{}'".format(filename))
        ckpt = torch.load(filename)
    return ckpt

def log_matrix(writer, mat, name, epoch, fig_size=(8,6), dpi=200):
    plt.switch_backend('agg')
    fig = plt.figure(figsize=fig_size, dpi=dpi)
    mat = mat.cpu().detach().numpy()
    if mat.ndim == 1:
        mat = mat[:, np.newaxis]
    plt.imshow(mat, cmap=plt.get_cmap('BuPu'))
    cbar = plt.colorbar()
    cbar.solids.set_edgecolor("face")

    plt.tight_layout()
    fig.canvas.draw()
    writer.add_image(name, tensorboardX.utils.figure_to_image(fig), epoch)

def denoise_graph(adj, node_idx, feat=None, label=None, threshold=0.1, threshold_num=12):
    num_nodes = adj.shape[-1]
    G = nx.Graph()
    G.add_nodes_from(range(num_nodes))
    G.node[node_idx]['self'] = 1
    #print('num nodes : ', G.number_of_nodes())
    if feat is not None:
        for node in G.nodes():
            G.node[node]['feat'] = feat[node]
    if label is not None:
        for node in G.nodes():
            G.node[node]['label'] = label[node] 

    if threshold_num is not None:
        adj += np.random.rand(adj.shape[0],adj.shape[1])*1e-4
        threshold = np.sort(adj[adj>0])[-threshold_num]
    weighted_edge_list = [(i, j, adj[i, j]) for i in range(num_nodes) for j in range(num_nodes) if
            adj[i,j] >= threshold]
    G.add_weighted_edges_from(weighted_edge_list)
    Gc = max(nx.connected_component_subgraphs(G), key=len)
    import pdb
    pdb.set_trace()
    return Gc

def log_graph(writer, Gc, name, identify_self=True, nodecolor='label', epoch=0, fig_size=(4,3),
        dpi=300, label_node_feat=False, edge_vmax=1.0):
    '''
    Args:
        nodecolor: the color of node, can be determined by 'label', or 'feat'. For feat, it needs to
            be one-hot'
    '''
    cmap = plt.get_cmap('Set1')
    plt.switch_backend('agg')
    fig = plt.figure(figsize=fig_size, dpi=dpi)
   
    node_colors = []
    edge_colors = [min(max(w, 0.0), 1.0) for (u,v,w) in Gc.edges.data('weight', default=1)]

    # maximum value for node color
    vmax = 8
    for i in Gc.nodes():
        if nodecolor == 'feat' and 'feat' in Gc.node[i]:
            num_classes = Gc.node[i]['feat'].size()[0]
            if num_classes >= 10:
                cmap = plt.get_cmap('tab20')
                vmax = 19
            elif num_classes >= 8:
                cmap = plt.get_cmap('tab10')
                vmax = 9
            break
      
    feat_labels={}
    for i in Gc.nodes():
        if identify_self and 'self' in Gc.node[i]:
            node_colors.append(0)
        elif nodecolor == 'label' and 'label' in Gc.node[i]:
            node_colors.append(Gc.node[i]['label'] + 1)
        elif nodecolor == 'feat' and 'feat' in Gc.node[i]:
            #print(Gc.node[i]['feat'])
            feat = Gc.node[i]['feat'].detach().numpy()
            # idx with pos val in 1D array
            feat_class = 0
            for j in range(len(feat)):
                if feat[j] == 1:
                    feat_class = j
                    break
            node_colors.append(feat_class)
            feat_labels[i] = feat_class
        else:
            node_colors.append(1)
    if not label_node_feat:
        feat_labels=None

    plt.switch_backend('agg')
    fig = plt.figure(figsize=fig_size, dpi=dpi)

    #pos_layout = nx.kamada_kawai_layout(Gc)
    pos_layout = nx.spring_layout(Gc)

    nx.draw(Gc, pos=nx.kamada_kawai_layout(Gc), with_labels=False, font_size=4, labels=feat_labels,
            node_color=node_colors, vmin=0, vmax=vmax, cmap=cmap,
            edge_color=edge_colors, edge_cmap=plt.get_cmap('Greys'), 
            edge_vmin=0.0,
            edge_vmax=edge_vmax,
            width=1.0, node_size=50,
            alpha=0.8)
    fig.axes[0].xaxis.set_visible(False)
    fig.canvas.draw()
    plt.savefig('log/' + name+'.png')
    img = tensorboardX.utils.figure_to_image(fig)
    writer.add_image(name, img, epoch)

def plot_cmap(cmap, ncolor):
    """ 
    A convenient function to plot colors of a matplotlib cmap
    Credit goes to http://gvallver.perso.univ-pau.fr/?p=712
 
    Args:
        ncolor (int): number of color to show
        cmap: a cmap object or a matplotlib color name
    """
 
    if isinstance(cmap, str):
        name = cmap
        try:
            cm = plt.get_cmap(cmap)
        except ValueError:
            print("WARNINGS :", cmap, " is not a known colormap")
            cm = plt.cm.gray
    else:
        cm = cmap
        name = cm.name
 
    with matplotlib.rc_context(matplotlib.rcParamsDefault):
        fig = plt.figure(figsize=(12, 1), frameon=False)
        ax = fig.add_subplot(111)
        ax.pcolor(np.linspace(1, ncolor, ncolor).reshape(1, ncolor), cmap=cm)
        ax.set_title(name)
        xt = ax.set_xticks([])
        yt = ax.set_yticks([])
    return fig

def plot_cmap_tb(writer, cmap, ncolor, name):
    fig = plot_cmap(cmap, ncolor)
    img = tensorboardX.utils.figure_to_image(fig)
    writer.add_image(name, img, 0)

