from GAN_Model import GAN_Model
from helpers.helpers import encode_sentences
from helpers.helpers import encode_sentences_one_hot
from helpers.helpers import addPadding
from helpers.helpers import addPadding_one_hot


from models.losses import wasserstein_disc
from models.losses import wasserstein_disc_split
from models.losses import wasserstein_gen
from models.losses import minimax_disc
from models.losses import minimax_gen
from models.losses import minimax_loss
from models.losses import diff_disc
from models.losses import diff_disc_split
from models.losses import diff_gen


from models.Generator import Generator
from models.Discriminator import Discriminator
import torch
from torch import nn
import numpy as np
import matplotlib.pyplot as plt
import os

from diffusion_resources.distributions import y_sample
from diffusion_resources.distributions import p_pie_sample
from diffusion_resources.schedulers import linear_variance_scheduler
from diffusion_resources.schedulers import T_scheduler



cpu = torch.device('cpu')
gpu = torch.device('cuda:0')




class Diff_GAN_Model(nn.Module):
    # Inputs:
    #   vocab - A dictionary of vocab where the keys are integers and the
    #           values are words
    #   M_gen - The number of blocks in the encoder part of the generator model
    #   N_gen - The number of blocks in the decoder part of the generator model
    #   N_disc - The number of blocks in the discriminator model
    #   batchSize - Size to bach data into
    #   embedding_size - The size of the vector to embed each word
    #   sequence_length - The max length of the sentence to train the model on
    #   num_heads - Number of heads for the MHA modules
    #   trainingRatio - 2-D array representing the number of epochs to 
    #                   train the generator (0) vs the discriminator (1)
    #   decRatRate - Decrease the ratio after every decRatRate steps. Use -1 to
    #                never decrease the ratio
    #   pooling - What pooling mode should be used? ("avg", "max", or "none")
    #   embed_mode - What embedding mode should be used for the
    #                generator? ("norm" or "custom")
    #   alpha - Learning rate of the model
    #   Lambda - Lambda value used for gradient penalty in disc loss
    #   Beta1 - Adam beta 1 term
    #   Beta2 - Adam beta 2 term
    #   device - Device to put the model on
    #   saveSteps - Number of steps until the model is saved
    #   saveDir - Directory to save the model to
    #   genSaveFile - Name of the file to save the generator model to
    #   discSaveFile - Name of the file to save the discriminator model to
    #   trainGraphFile - File to save training graph during training
    #   TgraphFile - File to save the T graph to
    #   loadInEpoch - Should the data be loaded in as needed instead of
    #                 before training (True if so, False to load before training)
    #   delWhenLoaded - Delete the data as it's loaded in to save space?
    #                   Note: This is automatically False if loadInEpoch is True
    #   Beta_0 - Lowest possible Beta value, when t is 0
    #   Beta_T - Highest possible Beta value, when t is T
    #   T_min - Min diffusion steps when corrupting the data
    #   T_max - Max diffusion steps when corrupting the data
    #   sigma - Addative noise weighting term
    #   d_target - Term used for the T scheduler denoting if the 
    #               T change should be positive of negative depending 
    #               on the disc output
    #   C - Constant for the T scheduler multiplying the change of T
    def __init__(self, vocab, M_gen, N_gen, N_disc, batchSize, embedding_size, sequence_length, num_heads, trainingRatio, decRatRate, pooling, embed_mode, alpha, Lambda, Beta1, Beta2, device, saveSteps, saveDir, genSaveFile, discSaveFile, trainGraphFile, TgraphFile, loadInEpoch, delWhenLoaded, Beta_0, Beta_T, T_min, T_max, sigma, d_target, C):
        super(Diff_GAN_Model, self).__init__()
        
        # The ratio must not have a lower value for the discriminator (1)
        assert trainingRatio[0]<=trainingRatio[1], "The training ratio must have a grater number in the zeroth index"
        
        # Save the needed variables
        self.vocab = vocab
        self.vocab_inv = {vocab[i]:i for i in vocab.keys()}
        self.sequence_length = sequence_length
        self.batchSize = batchSize
        self.trainingRatio = trainingRatio
        self.decRatRate = decRatRate
        self.Lambda = Lambda
        self.embed_mode = embed_mode
        self.loadInEpoch = loadInEpoch
        self.delWhenLoaded = delWhenLoaded if self.loadInEpoch == False else False
        
        # Saving paramters
        self.saveSteps = saveSteps
        self.saveDir = saveDir
        self.genSaveFile = genSaveFile
        self.discSaveFile = discSaveFile
        self.trainGraphFile = trainGraphFile
        self.TgraphFile = TgraphFile
        
        # Diffusion parameters
        self.Beta_0 = Beta_0
        self.Beta_T = Beta_T
        self.T_min = T_min
        self.T_max = T_max
        self.sigma = sigma
        self.d_target = d_target
        self.C = C

        # Convert the device to a torch device
        if device.lower() == "fullgpu":
            if torch.cuda.is_available():
                dev = device.lower()
                device = torch.device('cuda:0')
            else:
                dev = "cpu"
                print("GPU not available, defaulting to CPU. Please ignore this message if you do not wish to use a GPU\n")
                device = torch.device('cpu')
        else:
            dev = device.lower()
            device = torch.device('cpu')
        self.device = device
        self.dev = dev
        
        # The generator and discriminator models
        if self.dev != "cpu":
            self.generator = Generator(vocab, M_gen, N_gen, batchSize, embedding_size, sequence_length, num_heads, embed_mode, gpu)
            self.discriminator = Discriminator(N_disc, "sigmoid", batchSize, len(vocab), embedding_size, sequence_length, num_heads, pooling, gpu)
        else:
            self.generator = Generator(vocab, M_gen, N_gen, batchSize, embedding_size, sequence_length, num_heads, embed_mode, device)
            self.discriminator = Discriminator(N_disc, "sigmoid", batchSize, len(vocab), embedding_size, sequence_length, num_heads, pooling, device)
        
        # The optimizer for the model
        self.optim_gen = torch.optim.Adam(self.generator.parameters(), alpha, betas=[Beta1, Beta2])
        self.optim_disc = torch.optim.Adam(self.discriminator.parameters(), alpha, betas=[Beta1, Beta2])
        
        # Schedulers and distriutions turned into classes (others
        # are functions)
        self.variance_scheduler = linear_variance_scheduler(Beta_0, Beta_T, T_max)
        
        # Setup T (diffusion timesteps) to be the minimum value
        self.T = T_min
        
        # Setup the t_epl array
        self.t_epl = np.zeros(64, dtype=np.float32)
        self.t_epl[32:] = p_pie_sample(32, self.T)
    
    
    
    # Update the model's diffusion paramters
    def update_diffusion(self, D_real):
        # Update the T equation using the T scheduler
        self.T = T_scheduler(self.T, self.d_target, self.C, D_real)
        
        # Clip T between T_min and T_max
        self.T = torch.clamp(self.T, self.T_min, self.T_max)
        
        # Update the t_epl array
        self.t_epl[32:] = p_pie_sample(32, self.T.cpu().detach())
    
    
    
    # Train the models
    # Input:
    #   X - A list of sentences to train the models on
    #   epochs - Number of epochs to train the models for
    def train_model(self, X, epochs):
        # Encode the sentences
        if self.loadInEpoch == False:
            X_orig_one_hot = np.array(encode_sentences_one_hot(X, self.vocab_inv, self.sequence_length, self.delWhenLoaded, self.device), dtype=object)
            s = X_orig_one_hot.shape[0]
        else:
            X = np.array(X, dtype=object)
            s = X.shape[0]
        
        # Save loss values over training for the loss plot
        self.genLoss = []
        self.discLoss = []
        self.discLoss_real = []
        self.discLoss_fake = []
        
        # Save the T value over training
        self.TVals = []
        
        # Train the model for epochs number of epochs
        for epoch in range(1, epochs+1):
            # Model saving
            if epoch % self.saveSteps == 0:
                self.saveModels(self.saveDir, self.genSaveFile, self.discSaveFile, epoch)
            
            # Create a list of indices which the Discriminator
            # has left to see and the Generator has left to see
            disc_nums = torch.randperm(s, device=self.device)
            
            # Step 1: Train the discriminator
            self.optim_disc.zero_grad()
            for i in range(0, max(self.trainingRatio[1], 1)):
                # Sample a batch of real data
                disc_sub = disc_nums[:self.batchSize]
                
                # Get a batch of data from the generator
                with torch.no_grad():
                    x_g = self.generator.forward_train()
                    
                # Get a real data subset using one_hot encoding
                if self.loadInEpoch == True:
                    # Load in more data until no more data is availble
                    # or the requested batch size is obtained
                    x = np.array([])
                    while x.shape[0] < self.batchSize or disc_nums.shape[0] == 0:
                        # Get more data if needed
                        disc_sub = disc_nums[:self.batchSize]
                        disc_nums = disc_nums[self.batchSize:]
                        
                        # Save the data
                        if len(x) == 0:
                            x = np.array(encode_sentences_one_hot(X[disc_sub.cpu().detach().numpy()].tolist(), self.vocab_inv, self.sequence_length, False, self.device), dtype=object)
                        else:
                            x = np.concatenate((x, np.array(encode_sentences_one_hot(X[disc_sub.cpu().detach().numpy()].tolist(), self.vocab_inv, self.sequence_length, False, self.device), dtype=object)[self.batchSize-x.shape[0]:]))
                    
                    # If disc_nums is empty, a problem occured
                    assert disc_nums.shape[0] > 0, "Not enough data under requested sequence langth"
                else:
                    x = X_orig_one_hot[disc_sub.cpu().detach().numpy()]
                
                # Get a batch of real data and add padding
                # to it
                if self.loadInEpoch == True:
                    x = np.array(encode_sentences_one_hot(X[disc_sub.cpu().detach().numpy()], self.vocab_inv, self.sequence_length, False, self.device), dtype=object)
                else:
                    x = X_orig_one_hot[disc_sub.cpu().detach().numpy()]
                x = addPadding_one_hot(x, self.vocab_inv, self.sequence_length)
                if self.dev == "partgpu":
                    x = x.to(gpu)
                else:
                    x = x.to(self.device)
                
                # Sample a batch of t values from t_epl
                t = torch.tensor(np.random.choice(self.t_epl, size=self.batchSize, replace=True))
                
                # Diffuse the real and fake data
                y = y_sample(x.float(), self.sigma, self.variance_scheduler, t)
                y_g = y_sample(x_g, self.sigma, self.variance_scheduler, t)
                
                # Delete the undiffused data
                del x, x_g
                
                # Get the discriminator value on the real and fake data
                disc_real = self.discriminator(y)
                disc_fake = self.discriminator(y_g)
                
                # Get the discriminator loss
                # which we want to maximize
                discLoss = -diff_disc(disc_real, disc_fake)
                
                discLoss_real, discLoss_fake = diff_disc_split(disc_real, disc_fake)
                
                # Backpropogate the cost
                discLoss.backward()
                
                # Step the optimizer
                self.optim_disc.step()
                self.optim_disc.zero_grad()
                
                discLoss *= -1
                
                # Delete all discriminator stuff as its no longer needed
                del disc_sub, disc_fake, y, y_g, t
            
            
            # Step 2: Train the generator
            self.optim_gen.zero_grad()
            for i in range(0, max(self.trainingRatio[0], 1)):
                # Get subset indices of the data for the generator
                # and discriminator
                disc_sub = disc_nums[:self.batchSize]
                
                # Get a batch of data from the generator
                x_g = self.generator.forward_train()
                
                # Sample a batch of t values from t_epl
                t = torch.tensor(np.random.choice(self.t_epl, size=self.batchSize, replace=True))
                
                # Diffuse the generated data
                y_g = y_sample(x_g, self.sigma, self.variance_scheduler, t)
                
                # Get the discriminator value on the diffused data
                disc_fake = self.discriminator(y_g)
                
                # Get the generator loss which we
                # want to minimize
                genLoss = diff_gen(disc_fake)
                
                # Backpropogate the loss
                genLoss.backward()
                
                # Step the optimizer
                self.optim_gen.step()
                self.optim_gen.zero_grad()
                
                # Delete the variables that are no longer needed
                del disc_sub, disc_nums, disc_fake, y_g, x_g, t
            
            # Step 3: Update the diffusion values every 4 steps
            if epoch % 4 == 0:
                self.update_diffusion(disc_real.cpu().detach())
            
            # Save the T value
            self.TVals.append(self.T)
            
            
            # Decrease the rate
            if self.decRatRate > 0:
                if epochs%self.decRatRate == 0 and self.decRatRate > 0:
                    self.trainingRatio[0] -= 1
                    self.trainingRatio[1] -= 1
                
            # Save the loss values
            self.genLoss.append(genLoss.item())
            self.discLoss.append(discLoss.item())
            self.discLoss_real.append(discLoss_real.item())
            self.discLoss_fake.append(discLoss_fake.item())
            
            print(f"Epoch: {epoch}   Generator Loss: {round(genLoss.item(), 4)}     Discriminator Loss Real: {round(discLoss_real.item(), 4)}     Discriminator Loss Fake: {round(discLoss_fake.item(), 4)}    Discriminator Loss: {round(discLoss.item(), 4)}    T: {self.T}\n")
    
    
    
    # Save the models and a training graph
    def saveModels(self, saveDir, genFile, discFile, epoch=None):
        if epoch == None:
            self.generator.saveModel(saveDir, genFile)
            self.discriminator.saveModel(saveDir, discFile)
        else:
            l = len(genFile.split(".")[-1])+1
            genFile = genFile[:-l] + f" - {epoch}.pkl"
            l = len(discFile.split(".")[-1])+1
            discFile = discFile[:-l] + f" - {epoch}.pkl"
            
            self.generator.saveModel(saveDir, genFile)
            self.discriminator.saveModel(saveDir, discFile)
            
            if self.trainGraphFile:
                # Training graph
                fix, ax = plt.subplots()
                y = [i for i in range(1, len(self.genLoss)+1)]
                ax.plot(y, self.genLoss, label="Gen loss")
                ax.plot(y, self.discLoss_real, label="Disc loss real")
                ax.plot(y, self.discLoss_fake, label="Disc loss fake")
                ax.plot(y, self.discLoss, label="Disc loss combined")
                ax.set_title("Gen and disc loss over epochs")
                ax.set_xlabel("Epochs")
                ax.set_ylabel("Loss")
                ax.legend()
                plt.savefig(self.saveDir + os.sep + self.trainGraphFile)
                plt.close()
                
                # T graph
                fix, ax = plt.subplots()
                y = [i for i in range(1, len(self.genLoss)+1)]
                ax.plot(y, self.TVals, label="T Values")
                ax.set_title("T values over epochs")
                ax.set_xlabel("Epochs")
                ax.set_ylabel("T value")
                ax.legend()
                plt.savefig(self.saveDir + os.sep + self.TgraphFile)
                plt.close()
    
    # Load the models
    def loadModels(self, loadDir, genFile, discFile):
        self.generator.loadModel(loadDir, genFile)
        self.discriminator.loadModel(loadDir, discFile)