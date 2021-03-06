# PyTorch_TextGen
A basic text generation model for a project I'm working on


Documentation/Log for GANs:
https://docs.google.com/document/d/1UA-dEF-IMr5-mOgkp6ORRtAERDEprKHw3K_Lw9A-vmU/edit?usp=sharing

Documentation/Log for networks that aren't GANs:
https://docs.google.com/document/d/1_2mnS_jRa5RixBPNazFUxKrX-_Y-Bz9zZHglUnGHpgo/edit?usp=sharing




# Problems and Solutions
- Problem: The output of the Generator was of shape (N, sequence length) where each batch sentence was the argmax of the softmax output. The problem is the argmax is not differentiable and a lot fo information is being lost with the argmax conversion. So, the generator isn't able to learn.
  - Solution: Instead of taking the argmax, the softmax outputs of the generator is directly used by the discriminator. So, the output of the generator is (N, sequence length, vocab size). The discriminator takes this output as input and uses a few linear layers to convert the tensor to the shape which was previously used of (N, sequence length, embedding size).
- Problem: The noise transformation in the generator was a heavy process that transformed a large latent space of data. The input used transformer blocks and MHA which is a lot of FLOPS (floating point operations) and very expensive. Additionally, since the output was 2-d, the generator had a hard time finding a good mapping for this noise.
  - Solution: Instead of trying to get 2-d noise from the generator, we can get 1-d and broadcast it to 2-d. So, we get N noise vector of size S (sequence length) and apply a few Linear transformations on that data. The output will also be NxS. Then, we broadcast the noise vector of size S by E (embedding size) so that the output is NxSxE. So now there are E number of noise vectors. This is the needed shape for the generator and since the embedding space is 1-d instead of 2-d, it seems to handle the noise a lot better.



Note: Data from the following README:
- Random Text: https://www.kaggle.com/datasets/kashnitsky/hierarchical-text-classification
- Fortunes 1: https://github.com/ruanyf/fortunes
- Fortunes 2: http://www.fortunecookiemessage.com/
