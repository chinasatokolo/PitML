# -*- coding: utf-8 -*-
"""
Transfer Learning for Pituitary Images
==========================
**Author**: `Chinasa T. Okolo`_

There are two major transfer learning scenarios:

-  **Finetuning the convnet**: Instead of random initialization,
   initialize the network with a pretrained network, like the one that is
   trained on imagenet 1000 dataset. Rest of the training is as
   usual.
-  **ConvNet as fixed feature extractor**: Here, will freeze the weights
   for all of the network except that of the final fully connected
   layer. This last fully connected layer is replaced with a new one
   with random weights and only this layer is trained.

Code for PyTorch model is adapted from work done by Sasank Chilamkurthy

"""
# Author: Chinasa Okolo

from __future__ import print_function, division

import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
from sklearn import metrics
from sklearn.metrics import roc_auc_score
import scikitplot as skplt
import numpy as np
import torchvision
from torchvision import datasets, models, transforms
import matplotlib.pyplot as plt
plt.switch_backend('agg')
import time
import os
import copy

plt.ion()   # interactive mode


######################################################################
# Load Data

# Data augmentation and normalization for training
# Just normalization for validation
data_transforms = {
    'train': transforms.Compose([
        transforms.RandomResizedCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    'val': transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
}

data_dir = 'data/pituitary_data'
image_datasets = {x: datasets.ImageFolder(os.path.join(data_dir, x),
                                          data_transforms[x])
                  for x in ['train', 'val']}
dataloaders = {x: torch.utils.data.DataLoader(image_datasets[x], batch_size=4,
                                             shuffle=True, num_workers=4)
              for x in ['train', 'val']}
dataset_sizes = {x: len(image_datasets[x]) for x in ['train', 'val']}
class_names = image_datasets['train'].classes
print(class_names)

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

######################################################################
# Visualize a few images
# ^^^^^^^^^^^^^^^^^^^^^^
# Let's visualize a few training images so as to understand the data
# augmentations.

def imshow(inp, title=None):
    """Imshow for Tensor."""
    inp = inp.numpy().transpose((1, 2, 0))
    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])
    inp = std * inp + mean
    inp = np.clip(inp, 0, 1)
    plt.imshow(inp)
    if title is not None:
        plt.title(title)
    plt.pause(0.001)  # pause a bit so that plots are updated


# Get a batch of training data
inputs, classes = next(iter(dataloaders['train']))

# Make a grid from batch
out = torchvision.utils.make_grid(inputs)

imshow(out, title=[class_names[x] for x in classes])


######################################################################
# Training the model
# ------------------
#
# Now, let's write a general function to train a model. Here, we will
# illustrate:
#
# -  Scheduling the learning rate
# -  Saving the best model
#
# In the following, parameter ``scheduler`` is an LR scheduler object from
# ``torch.optim.lr_scheduler``.


def train_model(model, criterion, optimizer, scheduler, num_epochs=25):
    since = time.time()

    train_val_losses = {'train': [],
                        'val': []
                       }
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(num_epochs):
        print('Epoch {}/{}'.format(epoch, num_epochs - 1))
        print('-' * 10)

        # Each epoch has a training and validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                scheduler.step()
                model.train()  # Set model to training mode
            else:
                model.eval()   # Set model to evaluate mode

            running_loss = 0.0
            running_corrects = 0

            # Iterate over data
            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                # Zero the parameter gradients
                optimizer.zero_grad()

                # Forward
                # Track history if only in train
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    # Backward + optimize only if in training phase
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                # Statistics
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.double() / dataset_sizes[phase]

            print('{} Loss: {:.4f} Acc: {:.4f}'.format(
                phase, epoch_loss, epoch_acc))
            print(preds)

            # Add information to loss dictionary
            train_val_losses[phase].append(epoch_loss)

            # Deep copy the model
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

        print(preds)

    # Training outcomes and metrics
    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
    print('Best val Acc: {:4f}'.format(best_acc))
    plot_learning_curve(train_val_losses.get('train'), train_val_losses.get('val'), num_epochs)

    # Load best model weights
    model.load_state_dict(best_model_wts)
    return model


######################################################################
# Plot the learning curve during training and validation
#
#
#


def plot_learning_curve(training_loss, validation_loss, num_epoch):

    # Initialize and form plot
    epoch_array = range(0, num_epoch)
    plt.figure()
    plt.plot(epoch_array, training_loss, 'b', label = 'Training loss')
    plt.hold()
    plt.plot(epoch_array, validation_loss, 'r', label = 'Validation loss')
    plt.legend(loc = 'lower right')

    plt.xlim([0, num_epoch])
    plt.ylim([0, 1])

    plt.xlabel('Epoch')
    plt.ylabel('Loss')

    plt.title('Training/Validation Loss over Time')
    plt.legend(loc = "lower right")
    plt.show()
    plt.savefig('Training_Validation_PitML.jpg')


######################################################################
# Compute ROC metrics for predictions
#
#
#

def compute_roc_metrics(groundtruth_labels, probs):

    # Compute ROC AUC Score
    true_labels = np.array(groundtruth_labels) # Numpy array of binary class for each tested image
    prob_scores = np.array(probs) # Numpy array of confidence percentages of each tested image
    auc_roc = roc_auc_score(true_labels, prob_scores)
    print('Computed ROC AUC Score: {}'.format(auc_roc))

    # Compute true and false positive rates
    fpr, tpr, thresholds = metrics.roc_curve(true_labels, prob_scores)
    print('False positive rate: {}'.format(fpr))
    print('True positive rate: {}'.format(tpr))

    # Plot computed metrics
    plt.figure()
    plt.plot(fpr, tpr, 'b', label = 'AUC = %0.2f' % auc_roc)
    plt.legend(loc = 'lower right')
    plt.plot([0, 1], [0, 1],'r--')

    plt.xlim([0, 1])
    plt.ylim([0, 1])

    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')

    plt.title('Receiver Operating Characteristic')
    plt.legend(loc = "lower right")
    plt.show()
    plt.savefig('ROC_PitML.jpg')


######################################################################
# Visualizing the model predictions
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
# Generic function to display predictions for a few images
#

def visualize_model(model, num_images=24):
    was_training = model.training
    model.eval()
    images_so_far = 0
    total = 0
    correct = 0
    probability = 0
    fig = plt.figure()
    prob_estimates = [] # Percentage values for predictions
    pred_estimates = [] # Binary class predictions
    pred_groundtruth = [] # Groundtruth labels

    with torch.no_grad():
        for i, (inputs, labels) in enumerate(dataloaders['val']):
            inputs = inputs.to(device)
            labels = labels.to(device)

            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)

            for j in range(inputs.size()[0]):
                images_so_far += 1
                ax = plt.subplot(num_images//6, 6, images_so_far)
                ax.axis('off')
                ax.set_title('Predicted: {}'.format(class_names[preds[j]]))
                imshow(inputs.cpu().data[j])

                # Model statistics
                total += labels.size(0)
                correct += (preds == labels).sum().item()
                probability = 100 * correct / total
                prob_estimates.append(probability)
                pred_estimates.append(preds[j].item())
                pred_groundtruth.append(labels[j].item())

                print('Accuracy of the network on test image: %d %%' % (
                    probability))

                # Stop testing images
                if images_so_far == num_images:
                    model.train(mode=was_training)

                    # Print array data
                    print('Groundtruth labels: {}'.format(pred_groundtruth))
                    print('Predicted labels: {}'.format(pred_estimates))
                    print('Confidence of predictions: {}'.format(prob_estimates))
                    compute_roc_metrics(pred_groundtruth, prob_estimates)
                    return

        model.train(mode=was_training)


######################################################################
# Finetuning the convnet
# ----------------------
#
# Load a pretrained model and reset final fully connected layer.
#

model_ft = models.resnet34(pretrained=True)
num_ftrs = model_ft.fc.in_features
model_ft.fc = nn.Linear(num_ftrs, 2)

model_ft = model_ft.to(device)

criterion = nn.CrossEntropyLoss()

# Observe that all parameters are being optimized
optimizer_ft = optim.SGD(model_ft.parameters(), lr=0.001, momentum=0.9)

# Decay LR by a factor of 0.1 every 7 epochs
exp_lr_scheduler = lr_scheduler.StepLR(optimizer_ft, step_size=7, gamma=0.1)


######################################################################
# Train and evaluate
# ^^^^^^^^^^^^^^^^^^
#

model_ft = train_model(model_ft, criterion, optimizer_ft, exp_lr_scheduler,
                       num_epochs=5)

# Visualize the model
visualize_model(model_ft)

######################################################################
# ConvNet as fixed feature extractor
# ----------------------------------
#
# Here, we need to freeze all the network except the final layer. We need
# to set ``requires_grad == False`` to freeze the parameters so that the
# gradients are not computed in ``backward()``.
#
# You can read more about this in the documentation
# `here <https://pytorch.org/docs/notes/autograd.html#excluding-subgraphs-from-backward>`__.
#

model_conv = torchvision.models.resnet18(pretrained=True)
for param in model_conv.parameters():
    param.requires_grad = False

# Parameters of newly constructed modules have requires_grad=True by default
num_ftrs = model_conv.fc.in_features
model_conv.fc = nn.Linear(num_ftrs, 2)

model_conv = model_conv.to(device)

criterion = nn.CrossEntropyLoss()

# Observe that only parameters of final layer are being optimized as
# opposed to before.
optimizer_conv = optim.SGD(model_conv.fc.parameters(), lr=0.001, momentum=0.9)

# Decay LR by a factor of 0.1 every 7 epochs
exp_lr_scheduler = lr_scheduler.StepLR(optimizer_conv, step_size=7, gamma=0.1)


######################################################################
# Train and evaluate
# ^^^^^^^^^^^^^^^^^^
#
# On CPU this will take about half the time compared to previous scenario.
# This is expected as gradients don't need to be computed for most of the
# network. However, forward does need to be computed.
#

model_conv = train_model(model_conv, criterion, optimizer_conv,
                         exp_lr_scheduler, num_epochs=5)


# Visualize testing of the optimized model

visualize_model(model_conv)

plt.ioff()
plt.show()
