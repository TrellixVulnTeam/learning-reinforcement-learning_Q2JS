# change to neural network  architeccture

import gym
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import optim as optim
from tensorboardX import SummaryWriter


# PATHS --------------------------------------------------------------------------------------------------------------
# global path to save DQN parameters after training:
SAVE_PATH = "./dqn_weights/test.pth"

# local path for JSON logger (currently not used effectively)
JSON_LOGDIR = "./logdirectory/learning_scalars.json"

# local path for tensorboardX logging
LOGDIR = "./logdirectory"

# HYPERPARAMETERS ----------------------------------------------------------------------------------------------------

# learning rate for stochastic gradient descent
LEARNING_RATE = 0.1

# Markov chain discount factor
# note: the discount factor isn't actually used in this problem
DISCOUNT = 0.99

# number of episodes over which agent will learn from environment
EPISODES = 60000

# maximum number of time steps within an episode before the episode is forcefully ended
MAX_TIMESTEP = 100

# the size of a single log within the experience replay. The format is [Y, obs1, obs2, obs3, obs4, action], which
# represents recording the target Q (Y), state (obs1-obs4), action (action)
EXPERIENCE_REPLAY_SIZE = 6

# size of experience replay is dictated by the number of episodes we want to be able to learn from.
# since the Q learning step is asynchronous in this version (4.4), we need to make an experience replay,
# a structure which holds recent transitions to learn from. This variable distinguishes the size of the
# experience replay.
NUM_EPISODES_TO_REMEMBER = 10

NUM_EPISODES_TO_RENDER = 1000

# learning happens asynchronously by extracting n nonconsecutive samples from the experience replay
# BUFFER_SIZE = 50

# every 5 episodes we go through learning process
LEARNING_INTERVAL = 5

# tensorboardX uses this object to write data to a tensorboard
writer = SummaryWriter(LOGDIR)

# NEURAL NETWORK 9---------------------------------------------------------------------------------------------

"""
Neural network estimates Q-value
NN estimates Q(S,A)
S = state = observation @t (4,)
A = action = one of possible actions @state (1,) [0 or 1 --> left or right]
Since this problem only has 2 actions at each time step (left or right) we will make the input into the neural network
a combination of S A.

Input: S.append(A) = (4,) + (1,) = (5,); np.zeros((5,)) = [0,0,0,0,0]
(first 4 digits are observation, last digit is action Q(S,A))

Output: floating point value denoting value of current state-action pair
"""


class DQNetwork(nn.Module):

    def __init__(self):
        super(DQNetwork, self).__init__()  # inherits properties from parent class

        # nn layers:
        # since there is no image data, only information based on the cart
        # position, cart velocity, pole angle, pole velocity, we will use linear (FC) layers instead of Conv. layers
        # todo: structure of NN still in testing
        #
        # https://pytorch.org/docs/stable/nn.html#linear

        self.fully_connected1 = nn.Linear(in_features=4, out_features=32)
        self.fully_connected2 = nn.Linear(in_features=32, out_features=2)
        # self.fully_connected3 = nn.Linear(in_features=128, out_features=64)
        # self.fully_connected4 = nn.Linear(in_features=64, out_features=2)
        # self.fully_connected3 = nn.Linear(in_features=3, out_features=2)
        # self.fully_connected4 = nn.Linear(in_features=2, out_features=1)

    # pytorch requires a forward pass implementation that determines how the network layers are used
    # todo: the structure and activations of NN are in still testing
    def forward(self, input_data):
        out = F.relu(self.fully_connected1(input_data))
        # out = F.relu(self.fully_connected2(out))
        # out = F.relu(self.fully_connected3(out))
        out = self.fully_connected2(out)
        # out = (self.fully_connected3(out))
        # out = self.fully_connected4(out)

        # to provide visibility into the network weight convergence
        #        writer.add_histogram("fwd pass weights", out)
        #         writer.add_scalar("out(0)", out[0])
        #         writer.add_scalar("out(1)", out[1])
        return out


# functions -------------------------------------------------------------------------------------------------------
"""
The following function performs a forward pass in the DQN (neural network) object.
It requires that we: pass in the state, and return the confidence values for the action space.
"""


def exploit_action(observation, env, DQN):
    # todo: test if this does anything; do we need to have a "requiregrad = false" in the tensor?
    # set network to evaluation mode
    DQN.eval()

    temp = torch.as_tensor(observation, dtype=torch.float)

    Q_values = DQN(temp)

    # compare Q_value and select the highest value one
    # sample if they're the same
    if Q_values[0] > Q_values[1]:
        return 0
    elif Q_values[0] < Q_values[1]:
        return 1
    else:
        return env.action_space.sample()


"""
This method returns the numeric Q value of the state, action pair.
It appends the action to the end of the observation, and it passes the combination into the network to return
the function estimate of the network directly. Returns tensor.
"""


def single_Q_val(observation, DQN):

    DQN.train()

    temp = torch.as_tensor(observation, dtype=torch.float)
    action = DQN(temp)

    # return axis that denotes desired Q value
    # if action[0] > action[1]:
    #     return action[0]
    # else:
    #     return action[1]
    return torch.max(action, dim=1, keepdim=False, out=None)


def multiple_Q_val(observation, action, DQN):

    DQN.train()

    temp = torch.as_tensor(observation, dtype=torch.float)
    Q = DQN(temp)

    # returns Q_value of (S ,A)
    return Q[range(action.size), action]


"""
Write data from interacting with environment to the data structure that stores the transition from s to s', and it's
accompanying target Q value. This method (at one point) was a queue (first in first out) which would hold only a recent
set of memories, but has since been changed in an attempt to debug. It currently has an amount of allocated space
which will be filled with memories during the interaction step of the algorithm, and then sampled to learn from
during the learning step (this allocated space is the experience replay). 

This method inserts the memory into the index, and increments the index to show the position of the most recent memory.
"""


def push_and_pop(Y, obs, act, exp_replay, index):

    # insert values into memory
    memory = np.hstack((float(Y), obs, float(act)))

    # insert memory into replay @ index
    exp_replay.append(memory)

    # index increment so that it shows the next available spot in the replay
    index += 1

    return index, exp_replay


# Algorithm Implementation/main ---------------------------------------------------------------------------------------


# global variables:
env = gym.make('CartPole-v0')
DQN = DQNetwork()
# DQN.load_state_dict(torch.load(SAVE_PATH))

"""
The core deep Q learning algorithm implementation with experience replay (utilizes helper functions)
"""


def run_training_operation():
    # declare optimizer: stochastic gradient descent with learning rate from global hyperparameter
    optimizer = optim.SGD(DQN.parameters(), lr=LEARNING_RATE)

    # declare MSE loss function
    loss_fn = nn.MSELoss()

    # declare experience replay
    # experience replay should store a recent set of memories
    # the data stored should resemble Y (asynchronous target Q), state, action (which derive Y). The idea is that
    # the Q value will be derived from the state and action synchronously, and Y will just be extracted as a scalar.
    # the loss will be calculated between the Q and Y over several samples from the memory. A batch of losses (sum)
    # will be used for the weight update.
    #
    # the first argument represents a the number of recent memories to remember, it is computed
    # in the "constants" section of the program.
    # the second argument represents the information that should be stored, Y (target Q), observation, action
    # experience_replay = np.zeros(((NUM_EPISODES_TO_REMEMBER * MAX_TIMESTEP), EXPERIENCE_REPLAY_SIZE))
    experience_replay = []

    # index that holds the index the next free
    pnp_idx = 0

    average_performance = 0

    # training loop for episodes
    for episode in range(EPISODES):

        # the algorithm needs to be "zero'd" before each episode so that results from previous episodes don't interfere
        # with results of current episodes
        if (episode % 100) == 0:
            print("Episode: ", episode)

        # time-step of current episode; incremented once in each repetition in the while loop
        time_step = 0

        # initialization & declaration of flag that breaks out of episode; changed when env returns "done"
        done = False

        # resetting environment returns initial observation
        observation = env.reset()

        # episode loops while the done flag isn't switched to "True" by the environment (terminal condition satisfied)
        # we also set a hard cap for the number of time steps we run
        while (done is not True) and (time_step < MAX_TIMESTEP):

            # epsilon greedy mechanism for selecting actions:

            # generate random number to be epsilon
            epsilon_rand = np.random.rand()

            # set exploration limit, a piecewise function that writes the limit based on what % of episodes we've run
            # while in 30% of episodes we set a limit of 0.99
            if average_performance < 10:
                current_explore_limit = 0.99
                for param_group in optimizer.param_groups:
                    param_group['lr'] = 0.7
            # while in 60% of episodes we set a limit of 0.5
            elif average_performance < 20:
                current_explore_limit = 0.7
                for param_group in optimizer.param_groups:
                    param_group['lr'] = 0.7
            # while in 80% of episodes we set a limit of 0.3

            elif average_performance < 35:
                current_explore_limit = 0.4
                for param_group in optimizer.param_groups:
                    param_group['lr'] = 0.4
            # the minimum explore limit is 0.1

            else:
                current_explore_limit = 0.
                for param_group in optimizer.param_groups:
                    param_group['lr'] = 0.125

            # keeping in mind the explore limit shrinks with time:
            # if epsilon is greater than the limit, we exploit our DQN, and select the best action
            # otherwise, most often in the beginning of the set of episodes, we sample the action space to explore
            # the state space of the simulation.
            if epsilon_rand >= current_explore_limit:
                action = exploit_action(observation, env, DQN)
            else:
                action = env.action_space.sample()  # take random (exploratory) action

            # interact with environment by taking an action at the current state (in DQN)
            # after interaction observe the consecutive state, reward from the transition, updated done flag
            next_observation, reward, done, _ = env.step(action=action)

            # when done is false, we don't need to learn, the episode terminated and there is no learning to be done (for cartpole)
            if done is False:
                # requirements for bellman equation to be stored in experience replay
                # fill the experience replay with info for Y, observation, action
                # Y = reward + Q(s', a') <-- value stored
                # Q = Q(s, a) <-- state and action  are  stored

                # compute optimal action' based on state'; to be used in calculating target Q
                # next_action = exploit_action(next_observation, env, DQN)

                # target Q value (Y) is the reward from (s,a) + Q(s',a')
                # the goal of the learning process is to produce a function that can approximate the target Q value
                temp = single_Q_val([next_observation], DQN)
                Y = reward + (DISCOUNT * temp[0].detach().numpy()[0])

                # store memory onto buffer
                # note:
                # pnp_idx denotes the next memory to be written. In the first episode, this value points to the
                # highest index value of a written memory, where values below index are memories, and values above are
                # zeros/whatever value was used to initialize the experience replay.
                # during non-first episodes, the value points to memory that can be overwritten; the experience
                # replay, however, is not cleared after the exp replay is exhausted, pnp_idx is, however, reset, so
                # new memories will overwrite the buffer values from the previous version of the experience replay
                pnp_idx, experience_replay = push_and_pop(Y, observation, action, experience_replay, pnp_idx)

            # update observatoin
            observation = next_observation

            # update time_step
            time_step += 1

            # end of time step, go back to while loop

        # learning step:
        # occurs every few episodes
        """
        learning step:
        perform the following n times:
                sample a memory from the experience replay
                compute mse loss for the sampled memory
                append mse loss to object
            sum mse losses
            back propagate mse loss with optimizer

        """
        if (episode % NUM_EPISODES_TO_REMEMBER) == 0 and (episode != 0):
            # policy loss will have the losses computed throughout the batches appended to it, it acts as a log
            # for the MSE loss computed between Q and Y (target Q)

            # todo: check the number of times we sample?
            # the learning step happens several times, in this version the number of samples is dictated by the number
            # of recent memories available from the last bit of learning

            # read memory data from data structure based on sampled index
            Y_exp_rep = torch.tensor(np.array(experience_replay)[:, 0])
            observation_exp_rep = np.array(experience_replay)[:, 1:5]
            action_exp_rep = np.array(experience_replay)[:, 5]

            # compute Q value estimate from neural network
            Q_exp_rep = multiple_Q_val(observation_exp_rep, action_exp_rep, DQN)

            # compute loss between target Q (Y) and estimated Q (Q)
            # mem_loss is the loss within a single memory, or transition
            policy_loss = loss_fn(Y_exp_rep.float(), Q_exp_rep)

            # back propagate with cumulative mse loss:

            # freeze gradients
            optimizer.zero_grad()

            # pytorch backward pass over sum of losses
            policy_loss.backward()

            # take optimizer step, propagating error and shifting weights w/ stochastic gradient descent
            optimizer.step()

            # zero pnp_index, this operation represents the notion of clearing experience memory
            # allows us to write from the start of the queue again at the interaction with env stage
            pnp_idx = 0
            experience_replay = []  # flush memory

        if (episode % NUM_EPISODES_TO_RENDER) == 0 and (episode != 0):
            # render the current controller
            average_performance = run_testing_operation(episode)

            writer.add_scalar('avg_performance', average_performance, episode)
            env.reset()
            # for _ in range(100):
            d = False
            while d is False:
                #env.render()
                _, _, d, _ = env.step(exploit_action(observation, env, DQN))  # take a random action
            env.close()

            for param_group in optimizer.param_groups:
                print("optimizer lr: ", param_group['lr'])

    # writer.export_scalars_to_json(JSON_LOGDIR)
    # save to local directory
    torch.save(DQN.state_dict(), SAVE_PATH)


def run_testing_operation(episode):
    num_runs = 30
    # DQN = DQNetwork()
    # DQN.load_state_dict(torch.load(SAVE_PATH))
    average_time = 0

    # print("episodes: {}".format(episode))
    for run in range(num_runs):
        observation = env.reset()
        time = 0
        reward_acc_test = 0

        for time_step in range(9000):

            # action = env.action_space.sample()
            action = exploit_action(observation, env, DQN)
            observation, reward, done, info = env.step(action)

            reward_acc_test += reward

            if done is True:
                break
            time += 1
        # writer.add_scalar("reward_acc_test", reward_acc_test, global_step=run)

        average_time += time
        # print("time for run {}: {}".format(run, time))
    avg = average_time / num_runs
    print("average time: ", (avg))
    return avg


# TEST SPACE

run_training_operation()

# run_testing_operation()

env.close()

# todo: eliminate env from exploit action so that implementation is cleaner (maybe faster cuz no calls to other methods)
# todo: make experience replay a class Instead of 2 arrays
# todo: implement multiple episodes as input to the learning algorithm, s.t. we can capture movement of the pole
# QUESTIONS FOR MAX:

# writer.close()
