from os import replace
import numpy as np
import torch
import torch.utils.data as data 
from gensim.models import word2vec
from torch.utils.data import dataset
from torch.utils.data.sampler import SequentialSampler
#from torch._six import int_classes as _int_classes
from torch.utils.data import DataLoader
import random 
#print(train_data.readlines())
input = []
IGNORE_ID=-1
def load_vocab(vocab_path, extra_word_list=[], encoding='utf8'):
    n = len(extra_word_list)
    with open(vocab_path, encoding=encoding) as vocab_file:
        vocab = { word.strip(): i + n for i, word in enumerate(vocab_file) }
    for i, word in enumerate(extra_word_list):
            vocab[word] = i
    return vocab


class NoPuncTextDataset(object):
    """
    Parse text without punctuation.
    Used by punctuation prediciton inference.
    """
    def __init__(self, txt_path, in_vocab_path, out_vocab_path):
        """Read txt file, input vocab and output vocab (punc vocab)."""
        self.txt_seqs = open(txt_path, encoding='utf8', errors='ignore').readlines()
        self.word2id = load_vocab(in_vocab_path,
                                        extra_word_list=["<UNK>", "<END>"])
        self.punc2id = load_vocab(out_vocab_path,
                                        extra_word_list=[" "])
        self.class2punc = { k : v for (v, k) in self.punc2id.items()}

    def __len__(self):
        """Return number of sentences in txt file."""
        return len(self.txt_seqs)

    def __getitem__(self, index):
        """Return input id sequence."""
        txt_seq = self.txt_seqs[index]
        word_id_seq = self._preprocess(txt_seq)
        return word_id_seq, txt_seq

    def _preprocess(self, txt_seq):
        """Convert txt sequence to word-id-seq."""
        input = []
        for token in txt_seq.split():
            input.append(self.word2id.get(token, self.word2id["<UNK>"]))
        input.append(self.word2id["<END>"])
        input = torch.LongTensor(input)
        return input

class TextAudioCollate(object):
    """Another way to implement collate_fn passed to DataLoader.
    Use class but not function because this is easier to pass some parameters.
    """
    def __init__(self):
        pass

    def __call__(self, batch, PAD=IGNORE_ID):
        """Process one mini-batch samples, such as sorting and padding.
        Args:
            batch: a list of (text sequence, audio feature sequence)
        Returns:
            input_padded_seqs
            label_padded_seqs
            lengths
        """
        # sort a list by sequence length (descending order) to use pack_padded_sequence
        batch.sort(key=lambda x: len(x[0]), reverse=True)
        # seperate inputs and labels
        input_seqs, label_seqs = zip(*batch)
        # padding
        lengths = [len(seq) for seq in input_seqs]
        input_padded_seqs = torch.zeros(len(input_seqs), max(lengths)).long()
        label_padded_seqs = torch.zeros(len(input_seqs), max(lengths)).fill_(PAD).long()
        for i, (input, label) in enumerate(zip(input_seqs, label_seqs)):
            end = lengths[i]
            input_padded_seqs[i, :end] = input[:end]
            label_padded_seqs[i, :end] = label[:end]
        return input_padded_seqs, torch.IntTensor(lengths), label_padded_seqs

class RandomBucketBatchSampler(object):
    """Yields of mini-batch of indices, sequential within the batch, random between batches.
    
    I.e. it works like bucket, but it also supports random between batches.
    Helpful for minimizing padding while retaining randomness with variable length inputs.
    Args:
        data_source (Dataset): dataset to sample from.
        batch_size (int): Size of mini-batch.
        drop_last (bool): If ``True``, the sampler will drop the last batch if
            its size would be less than ``batch_size``
    """
    def __init__(self, data_source, batch_size, drop_last):
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or \
                batch_size <= 0:
            raise ValueError("batch_size should be a positive integeral value, "
                             "but got batch_size={}".format(batch_size))
        if not isinstance(drop_last, bool):
            raise ValueError("drop_last should be a boolean value, but got "
                             "drop_last={}".format(drop_last))
        self.sampler = SequentialSampler(data_source) # impl sequential within the batch
        self.batch_size = batch_size
        self.drop_last = drop_last
        self.random_batches = self._make_batches() # impl random between batches

    def _make_batches(self):
        indices = [i for i in self.sampler]
        batches = [indices[i:i+self.batch_size]
                   for i in range(0, len(indices), self.batch_size)]
        if self.drop_last and len(self.sampler) % self.batch_size > 0:
            random_indices = torch.randperm(len(batches)-1).tolist() + [len(batches)-1]
        else:
            random_indices = torch.randperm(len(batches)).tolist()
        return [batches[i] for i in random_indices]

    def __iter__(self):
        for batch in self.random_batches:
            yield batch

    def __len__(self):
        return len(self.random_batches)


class PuncDataset(data.Dataset):
    """Custom Dataset for punctuation prediction."""
    def __init__(self, txt_path, in_vocab_path, out_vocab_path, sort=True):
        """Read txt file, input vocab and output vocab (punc vocab)."""
        self.txt_seqs = open(txt_path, encoding='utf8', errors='ignore').readlines()
        #self.txt_seqs = self.txt_seqs.replace('<questionmark>','<period>').replace('<period>','<period>|').split("|")
        #print(self.txt_seqs)
        self.word2id = load_vocab(in_vocab_path,
                                        extra_word_list=["<UNK>", "<END>"])
        self.punc2id = load_vocab(out_vocab_path,
                                        extra_word_list=[" "])
        if sort:
            # Also need to sort in collate_fn cause the sentence length will
            # change after self.preprocess()
            self.txt_seqs.sort(key=lambda x: len(x.split()), reverse=True)
        L=[random.randint(0,49000) for _ in range(5000) ] 
        for i in self.txt_seqs:
            #print("sentnece: ",i)
            if len(i) < 10:
                self.txt_seqs.remove(i)
        self.txt_seqs = [self.txt_seqs[s] for s in L]
        print("txt_seqs: ",len(self.txt_seqs))
    def __len__(self):
        """Return number of sentences in txt file."""
        return len(self.txt_seqs)

    def __getitem__(self, index):
        """Return one Tensor pair of (input id sequence, punc id sequence)."""
        txt_seq = self.txt_seqs[index]
        word_id_seq, punc_id_seq = self._preprocess(txt_seq)
        return word_id_seq, punc_id_seq
    def _preprocess(self, txt_seq):
        """Convert txt sequence to word-id-seq and punc-id-seq."""
        input = []
        label = []
        punc = " "
        #print(self.word2id)
        for token in txt_seq.split():
            if token in self.punc2id:
                punc = token
            else:
                input.append(self.word2id.get(token, self.word2id["<UNK>"]))
                label.append(self.punc2id[punc])
                punc = " "
        input.append(self.word2id["<END>"])
        label.append(self.punc2id[punc])
        
        input = torch.LongTensor(input)
        label = torch.LongTensor(label)
        
        # input = np.array(input)
        # label = np.array(label)
        #print(input)
        return input, label
    '''def _preprocess(self, txt_seq):
        """Convert txt sequence to word-id-seq and punc-id-seq."""
        input = []
        label = []
        punc = " "
        txt_ls = txt_seq.split()
        padded_length = txt_ls.count('<comma>')+txt_ls.count('<period>')+20
        if len(txt_ls) < padded_length+1:
            txt_ls += ['<UNK>' for i in range((padded_length-len(txt_ls)+1))]
        else:
            txt_ls = txt_ls[0:padded_length+1]
        i = 0
        count = 0
        while count < 20:
            if txt_ls[i] in self.punc2id:
                punc = txt_ls[i]
                i+=1
            else:
                count+=1
                i+=1
                input.append(self.word2id.get(txt_ls[i], self.word2id["<UNK>"]))
                label.append(self.punc2id[punc])
                punc = " "
        
        for token in txt_seq.split():
            if token in self.punc2id:
                punc = token
            else:
                input.append(self.word2id.get(token, self.word2id["<UNK>"]))
                label.append(self.punc2id[punc])
                punc = " "
        
        
        input.append(self.word2id["<END>"])
        label.append(self.punc2id[punc])
        input = torch.LongTensor(input)
        label = torch.LongTensor(label)
        return input, label
    '''
class TextAudioCollate(object):
    """Another way to implement collate_fn passed to DataLoader.
    Use class but not function because this is easier to pass some parameters.
    """
    def __init__(self):
        pass

    def __call__(self, batch, PAD=-1):
        """Process one mini-batch samples, such as sorting and padding.
        Args:
            batch: a list of (text sequence, audio feature sequence)
        Returns:
            input_padded_seqs
            label_padded_seqs
            lengths
        """
        # sort a list by sequence length (descending order) to use pack_padded_sequence
        batch.sort(key=lambda x: len(x[0]), reverse=True)
        # seperate inputs and labels
        input_seqs, label_seqs = zip(*batch)
        # padding
        lengths = [len(seq) for seq in input_seqs]
        input_padded_seqs = torch.zeros(len(input_seqs), max(lengths)).long()
        label_padded_seqs = torch.zeros(len(input_seqs), max(lengths)).fill_(PAD).long()
        for i, (input, label) in enumerate(zip(input_seqs, label_seqs)):
            end = lengths[i]
            input_padded_seqs[i, :end] = input[:end]
            label_padded_seqs[i, :end] = label[:end]
        return input_padded_seqs, torch.IntTensor(lengths), label_padded_seqs


def build_data_loader(txt_path, in_vocab_path, out_vocab_path,
                      batch_size=1, drop_last=False, num_workers=0):
    """Return data loader for custom dataset.
    """
    dataset = PuncDataset(txt_path, in_vocab_path, out_vocab_path)
    batch_sampler = RandomBucketBatchSampler(dataset,
                                             batch_size=batch_size,
                                             drop_last=drop_last)
    collate_fn = TextAudioCollate()
    data_loader = DataLoader(dataset, batch_sampler=batch_sampler,
                             collate_fn=collate_fn,num_workers=num_workers)
    return data_loader


    