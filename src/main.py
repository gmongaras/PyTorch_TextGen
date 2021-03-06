import torch
from Diff_GAN_Model import Diff_GAN_Model
from GAN_Model import GAN_Model
from Norm_Model import Norm_Model
from helpers.helpers import loadVocab






def main():
    # Paramters
    input_file = "data/Fortunes/data.txt"
    vocab_file = "vocab_fortunes.csv"
    
    # Saving/Loading paramters
    saveDir = "models-gumb"
    genSaveFile = "gen_model.pkl"
    discSaveFile = "disc_model.pkl"
    trainGraphFile = "trainGraph.png"
    TgraphFile = "TGraph.png" # Only used for diffusion GAN
    
    loadDir = "models-gumb"
    genLoadFile = "gen_model.pkl"
    discLoadFile = "disc_model.pkl"
    
    
    
    ### Load in the data ###
    sentences = []
    max = 100000   # Max number of sentences to load in
    i = 0
    with open(input_file, "r", encoding='windows-1252') as file:
        for line in file:
            if i == max:
                break
            i += 1
            sentences.append(line.strip())
    
    
    ### Load in the vocab ###    
    vocab = loadVocab(vocab_file)
    
    
    ### Create the model ###
    
    # Model paramters
    M_gen = 6                # Number of noise encoding blocks in the generator
    B_gen = 6                # Number of generator blocks in the generator
    O_gen = 2                # Number of MHA blocks in the generator
    gausNoise = True         # True to add pure gaussian noise in the generator output
                             # encoding, False to not add this noise
    T_disc = 6               # Number of transformer blocks in each discriminator block
    B_disc = 4               # Number of discriminator blocks in the discriminator
    O_disc = 2               # Number of output MHA blocks in the discrimiantor
    batchSize = 64           # Batch size for the entire model
    embedding_size_gen = 64  # Embedding size of the generator
    embedding_size_disc = 64 # Embedding size of the discriminator
                             # Note: If using PCA, keep this value small
    sequence_length = 64     # Sequence size to train the model with
    num_heads = 8            # Number of heads in each MHA block
    
    # Training parameters
    trainingMode = "gan"        # How should the models be trained ("gan", "diff", or "norm")
    pooling = "avg"             # Pooling mode for the discriminator blocks ("avg", "max", or "none")
    gen_outEnc_mode = "norm"    # How should the outputs of the generator be encoded? ("norm" or "gumb")
    embed_mode_gen = "norm"     # Embedding mode for the generator ("norm" or "custom")
    embed_mode_disc = "fc"      # Embedding mode for the discriminator ("fc" or "pca")
    alpha = 0.0001              # Model learning rate
    Beta1 = 0                   # Adam beta 1 term
    Beta2 = 0.9                 # Adam beta 2 term
    Lambda = 10                 # Lambda value used for gradient penalty in disc loss
    device = "partgpu"          # cpu, partgpu, or fullgpu
    epochs = 300000             # Number of epoch to train the model
    trainingRatio = [1, 6]      # Number of epochs to train the generator (0) vs the discriminator (1)
    decRatRate = -1             # Decrease the ratio after every decRatRate steps (-1 for not decrease)
    saveSteps = 1000            # Number of steps until the model is saved
    loadInEpoch = False         # Should the data be loaded in as needed instead of
                                # before training (True if so, False to load before training)
    delWhenLoaded = True        # Delete the data as it's loaded in to save space?
                                # Note: This is automatically False if loadInEpoch is True
    
    # Diffusion GAN parameters (if used)
    Beta_0 = 0.0001             # Lowest possible Beta value, when t is 0
    Beta_T = 0.02               # Highest possible Beta value, when t is T
    T_min = 5                   # Min diffusion steps when corrupting the data
    T_max = 500                 # Max diffusion steps when corrupting the data
    sigma = 0.5                 # Standard deviation of the noise to add to the data
    d_target = 0.6              # Term used for the T scheduler denoting if the T change should
                                # be positive of negative depending on the disc output
    C = 1                       # Constant for the T scheduler multiplying the change of T
    
    # Create the model
    if trainingMode.lower() == "diff":
        model = Diff_GAN_Model(vocab, M_gen, B_gen, O_gen, gausNoise,
                T_disc, B_disc, O_disc, 
                batchSize, embedding_size_gen, embedding_size_disc,
                sequence_length, num_heads,
                trainingRatio, decRatRate, pooling, gen_outEnc_mode,
                embed_mode_gen, embed_mode_disc,
                alpha, Lambda,
                Beta1, Beta2, device, saveSteps, saveDir, 
                genSaveFile, discSaveFile, trainGraphFile,
                TgraphFile, loadInEpoch, delWhenLoaded,
                Beta_0, Beta_T, T_min, T_max, sigma, d_target, C)
    elif trainingMode.lower() == "gan":
        model = GAN_Model(vocab, M_gen, B_gen, O_gen, gausNoise,
                T_disc, B_disc, O_disc, 
                batchSize, embedding_size_gen, embedding_size_disc,
                sequence_length, num_heads,
                trainingRatio, decRatRate, pooling, gen_outEnc_mode,
                embed_mode_gen, embed_mode_disc,
                alpha, Lambda,
                Beta1, Beta2, device, saveSteps, saveDir, 
                genSaveFile, discSaveFile, trainGraphFile,
                loadInEpoch, delWhenLoaded)
    else:
        model = Norm_Model(vocab, M_gen, B_gen, O_gen, gausNoise,
                batchSize, embedding_size_gen, sequence_length, num_heads,
                gen_outEnc_mode, embed_mode_gen, alpha, Lambda,
                Beta1, Beta2, device, saveSteps, saveDir, genSaveFile,
                trainGraphFile, loadInEpoch, delWhenLoaded)
    
    
    ### Training The Model ###
    #model.loadModels(loadDir, genLoadFile, discLoadFile)
    model.train_model(sentences, epochs)
    print()
    
    
    ### Model Saving and Predictions ###
    noise = torch.rand((sequence_length), requires_grad=False)
    out = model.generator(noise)
    for i in out:
        print(vocab[i.item()], end=" ")
    
    
main()
