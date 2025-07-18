# -*- coding: utf-8 -*-
"""stablelm_trial1.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1PwaQBs60Oeff-Htt4ypOR_UjnbiTW5kZ
"""

from google.colab import drive
drive.mount('/content/drive')

!pip install -q transformers datasets accelerate peft bitsandbytes
!pip install -q pandas numpy matplotlib seaborn scikit-learn

!pip install numpy==1.26.4

import os, gc, json, warnings
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns

from transformers import (
    AutoTokenizer, AutoModelForCausalLM,
    TrainingArguments, Trainer, DataCollatorForSeq2Seq,
    BitsAndBytesConfig, EarlyStoppingCallback
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
from datasets import Dataset as HFDataset

class Config:
    # Model configuration - Optimized for StableLM 3B 4e1t
    MODEL_NAME = "stabilityai/stablelm-3b-4e1t"
    MAX_LENGTH = 1648  # StableLM supports longer sequences efficiently
    NUM_EPOCHS = 3

    # Batch sizes - Optimized for effective batch size = 8
    TRAIN_BATCH_SIZE = 2    # Smaller due to larger model
    EVAL_BATCH_SIZE = 4     # Can be larger for eval
    GRAD_ACC_STEPS = 4      # 2 * 4 = 8 effective batch size

    # Learning rate - Optimized for StableLM and fast training without overfitting
    LEARNING_RATE = 1e-4    # Conservative for larger model
    WARMUP_STEPS = 100      # More warmup for stability
    WARMUP_RATIO = 0.05     # Lower warmup ratio

    # File paths
    DATASET_DIR = "/content/drive/MyDrive/final_benchmark_dataset"
    TRAIN_PATH = f"{DATASET_DIR}/train.jsonl"
    VAL_PATH = f"{DATASET_DIR}/val.jsonl"
    TEST_PATH = f"{DATASET_DIR}/test.jsonl"

    # Output paths
    OUTPUT_DIR = "/content/drive/MyDrive/stablelm_medical_checkpoints"
    LOGS_DIR = "/content/drive/MyDrive/stablelm_logs"
    MERGED_DIR = "/content/drive/MyDrive/stablelm_merged"

    # LoRA parameters - Optimized for StableLM 3B
    LORA_R = 16             # Lower rank for larger model to prevent overfitting
    LORA_ALPHA = 32         # 2x rank ratio
    LORA_DROPOUT = 0.1      # Standard dropout


    # Target modules for StableLM 3B (based on GPT-NeoX architecture)
    TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj", "gate_proj"]
    #TARGET_MODULES = ["query_key_value", "dense", "dense_h_to_4h", "dense_4h_to_h"]

config = Config()
warnings.filterwarnings('ignore')
tqdm.pandas()

# Check device
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"✅ Device: {device}")

if torch.cuda.is_available():
    print(f"🔥 GPU: {torch.cuda.get_device_name()}")
    print(f"💾 GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

def load_jsonl(path):
    """Load JSONL file with error handling"""
    try:
        with open(path, "r", encoding='utf-8') as f:
            data = [json.loads(line.strip()) for line in f if line.strip()]
        print(f"✅ Loaded {len(data)} samples from {path}")
        return data
    except FileNotFoundError:
        print(f"❌ File not found: {path}")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        return []

def load_and_prepare_data():
    """Load and prepare all datasets - Full dataset (no subset)"""
    print("📂 Loading full datasets...")

    train = load_jsonl(config.TRAIN_PATH)
    val = load_jsonl(config.VAL_PATH)
    test = load_jsonl(config.TEST_PATH)

    if not train or not val or not test:
        raise ValueError("❌ One or more datasets are empty!")

    print(f"📊 Full dataset sizes - Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    return (
        HFDataset.from_list(train),
        HFDataset.from_list(val),
        HFDataset.from_list(test)
    )

# Load datasets
train_ds, val_ds, test_ds = load_and_prepare_data()

# Load tokenizer
print("🔤 Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(config.MODEL_NAME, use_fast=True)

# StableLM specific tokenizer setup
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print(f"✅ Tokenizer loaded. Vocab size: {tokenizer.vocab_size}")

def tokenize_function(examples):
    """
    Optimized tokenization for StableLM 3B with instruction masking
    StableLM uses a different prompt format optimized for instruction following
    """
    instructions = examples["instruction"]
    outputs = examples["output"]
    model_inputs = {"input_ids": [], "attention_mask": [], "labels": []}

    for instruction, output in zip(instructions, outputs):
        # StableLM-optimized prompt format
        prompt = f"""<|system|>
You are a highly skilled medical AI assistant specialized in generating comprehensive, accurate medical discharge reports. You have extensive knowledge of medical terminology, procedures, and documentation standards.

<|user|>
{instruction}

<|assistant|>
"""

        # Create the full text (prompt + response)
        full_text = prompt + output + tokenizer.eos_token

        # Tokenize the full text
        tokenized = tokenizer(
            full_text,
            max_length=config.MAX_LENGTH,
            truncation=True,
            padding=False,
            return_tensors=None
        )

        # Tokenize just the prompt to get its length
        prompt_tokens = tokenizer(
            prompt,
            truncation=True,
            padding=False,
            return_tensors=None
        )

        input_ids = tokenized["input_ids"]
        attention_mask = tokenized["attention_mask"]
        labels = input_ids.copy()

        # Mask the prompt part in labels (set to -100)
        prompt_len = len(prompt_tokens["input_ids"])
        if prompt_len < len(labels):
            labels[:prompt_len] = [-100] * prompt_len
        else:
            # If prompt is too long, skip this example
            continue

        # Add to batch
        model_inputs["input_ids"].append(input_ids)
        model_inputs["attention_mask"].append(attention_mask)
        model_inputs["labels"].append(labels)

    return model_inputs

# Tokenize datasets
print("🔄 Tokenizing datasets...")
tokenized_train = train_ds.map(
    tokenize_function,
    batched=True,
    remove_columns=train_ds.column_names,
    desc="Tokenizing training data"
)

tokenized_val = val_ds.map(
    tokenize_function,
    batched=True,
    remove_columns=val_ds.column_names,
    desc="Tokenizing validation data"
)

print(f"✅ Tokenization complete!")
print(f"📊 Tokenized - Train: {len(tokenized_train)}, Val: {len(tokenized_val)}")

# Add length column for efficient batching
def add_length(example):
    return {"length": len(example["input_ids"])}

tokenized_train = tokenized_train.map(add_length, desc="Adding length column to train")
tokenized_val = tokenized_val.map(add_length, desc="Adding length column to val")

print("✅ Length columns added")

# Load model with quantization - Optimized for StableLM 3B
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16
)

print("🤖 Loading StableLM 3B 4e1t model...")
model = AutoModelForCausalLM.from_pretrained(
    config.MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
    trust_remote_code=True,
    use_cache=False
)

model.config.use_cache = False
model = prepare_model_for_kbit_training(model)

print("🔧 Setting up LoRA...")
lora_config = LoraConfig(
    r=config.LORA_R,
    lora_alpha=config.LORA_ALPHA,
    lora_dropout=config.LORA_DROPOUT,
    target_modules=config.TARGET_MODULES,
    bias="none",
    task_type=TaskType.CAUSAL_LM
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

print("✅ Model and LoRA setup complete")

# Create output directories
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
os.makedirs(config.LOGS_DIR, exist_ok=True)

# Training arguments - Optimized for StableLM 3B
training_args = TrainingArguments(
    output_dir=config.OUTPUT_DIR,
    num_train_epochs=config.NUM_EPOCHS,
    per_device_train_batch_size=config.TRAIN_BATCH_SIZE,
    per_device_eval_batch_size=config.EVAL_BATCH_SIZE,
    gradient_accumulation_steps=config.GRAD_ACC_STEPS,
    learning_rate=config.LEARNING_RATE,

    # Optimized scheduler for stability
    lr_scheduler_type="cosine",
    warmup_ratio=config.WARMUP_RATIO,
    warmup_steps=config.WARMUP_STEPS,

    # Evaluation and saving
    save_strategy="steps",
    eval_strategy="steps",
    save_steps=150,  # Less frequent for larger model
    eval_steps=150,
    logging_steps=50,

    # Model selection
    load_best_model_at_end=True,
    save_total_limit=2,  # Keep more checkpoints for safety
    metric_for_best_model="eval_loss",
    greater_is_better=False,

    # Performance optimizations for StableLM 3B
    fp16=False,  # Use bf16 instead for better stability
    bf16=True,
    gradient_checkpointing=True,
    dataloader_pin_memory=True,
    dataloader_num_workers=2,

    # Memory optimization
    ddp_find_unused_parameters=False,
    dataloader_drop_last=True,

    # Efficient batching
    group_by_length=True,
    length_column_name="length",

    # Regularization - Important for preventing overfitting
    weight_decay=0.01,
    max_grad_norm=1.0,

    # Other settings
    prediction_loss_only=True,
    report_to="none",
    logging_dir=config.LOGS_DIR,
    save_safetensors=True,
    remove_unused_columns=False,
    eval_accumulation_steps=1,

    # Stability improvements
    optim="adamw_torch",
    adam_beta1=0.9,
    adam_beta2=0.999,
    adam_epsilon=1e-8,
)

# Data collator
print("🔧 Setting up data collator...")
data_collator = DataCollatorForSeq2Seq(
    tokenizer=tokenizer,
    model=model,
    padding="longest",
    label_pad_token_id=-100,
    return_tensors="pt"
)

# Create trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_train,
    eval_dataset=tokenized_val,
    tokenizer=tokenizer,
    data_collator=data_collator,
    callbacks=[EarlyStoppingCallback(early_stopping_patience=5)]  # Higher patience for stability
)

print("✅ Trainer setup complete")

def start_training():
    """Start training with comprehensive monitoring"""
    gc.collect()
    torch.cuda.empty_cache()

    print("🚀 Starting StableLM 3B 4e1t Medical Fine-tuning (3 Epochs)...")
    print("=" * 60)
    print(f"🤖 Model: {config.MODEL_NAME}")
    print(f"📊 Training samples: {len(tokenized_train)}")
    print(f"📊 Validation samples: {len(tokenized_val)}")
    print(f"🎯 Train batch size: {config.TRAIN_BATCH_SIZE}")
    print(f"🎯 Eval batch size: {config.EVAL_BATCH_SIZE}")
    print(f"🔄 Gradient accumulation: {config.GRAD_ACC_STEPS}")
    print(f"🔥 Effective batch size: {config.TRAIN_BATCH_SIZE * config.GRAD_ACC_STEPS}")
    print(f"📏 Max sequence length: {config.MAX_LENGTH}")
    print(f"📈 Learning rate: {config.LEARNING_RATE}")
    print(f"🔁 Epochs: {config.NUM_EPOCHS}")
    print(f"🎯 LoRA rank: {config.LORA_R}")
    print(f"🎯 LoRA alpha: {config.LORA_ALPHA}")
    print(f"🎯 LoRA dropout: {config.LORA_DROPOUT}")
    print("=" * 60)

    if torch.cuda.is_available():
        print(f"🔥 GPU: {torch.cuda.get_device_name()}")
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        print(f"📊 GPU Memory - Allocated: {allocated:.2f} GB, Reserved: {reserved:.2f} GB")

    try:
        # Start training
        train_result = trainer.train(resume_from_checkpoint="/content/drive/MyDrive/stablelm_medical_checkpoints/checkpoint-450")
        #train_result = trainer.train()

        print("\n🎉 Training completed successfully!")
        print(f"📉 Final training loss: {train_result.training_loss:.4f}")
        print(f"⏱️ Training time: {train_result.training_time:.2f} seconds")

        # Save model
        trainer.save_model()
        print(f"💾 Model saved to: {config.OUTPUT_DIR}")

        return train_result

    except torch.cuda.OutOfMemoryError:
        print("❌ CUDA Out of Memory!")
        print("💡 Try reducing batch size or sequence length")
        print(f"Current: batch_size={config.TRAIN_BATCH_SIZE}, max_length={config.MAX_LENGTH}")
        print(f"Suggested: batch_size=1, grad_acc_steps=8")

        gc.collect()
        torch.cuda.empty_cache()
        return None

    except Exception as e:
        print(f"❌ Training error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# Start training
train_result = start_training()

if train_result is not None:
    print("\n🔄 Saving final model...")
    trainer.save_model(config.OUTPUT_DIR)
    tokenizer.save_pretrained(config.OUTPUT_DIR)
    print(f"✅ Model + tokenizer saved at {config.OUTPUT_DIR}")

    # Merge and save full model
    print("🔄 Merging LoRA weights...")
    from peft import PeftModel

    # Clear GPU memory first
    del model, trainer
    gc.collect()
    torch.cuda.empty_cache()

    # Load base model for merging
    base_model = AutoModelForCausalLM.from_pretrained(
        config.MODEL_NAME,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True
    )

    # Load and merge LoRA weights
    merged_model = PeftModel.from_pretrained(base_model, config.OUTPUT_DIR)
    merged_model = merged_model.merge_and_unload()

    # Save merged model
    os.makedirs(config.MERGED_DIR, exist_ok=True)
    merged_model.save_pretrained(config.MERGED_DIR, safe_serialization=True)
    tokenizer.save_pretrained(config.MERGED_DIR)

    print(f"✅ Fully merged model saved to: {config.MERGED_DIR}")

    # Clear memory
    del merged_model, base_model
    gc.collect()
    torch.cuda.empty_cache()

else:
    print("❌ Training failed, model not saved")

print("\n🎯 StableLM 3B 4e1t training script complete!")
print("=" * 60)
print("📊 OPTIMIZATIONS FOR STABLELM 3B 4e1t:")
print(f"• Model: TinyLlama-1.1B → StableLM-3B-4e1t")
print(f"• Train batch size: 8 → 2 (larger model)")
print(f"• Gradient accumulation: 1 → 4 (maintain effective batch size = 8)")
print(f"• Learning rate: 2e-4 → 1e-4 (conservative for larger model)")
print(f"• Max length: 1024 → 2048 (StableLM supports longer sequences)")
print(f"• LoRA rank: 32 → 16 (prevent overfitting)")
print(f"• LoRA alpha: 64 → 32 (2x rank ratio)")
print(f"• Target modules: Updated for GPT-NeoX architecture")
print(f"• Prompt format: Optimized for StableLM instruction following")
print(f"• Precision: fp16 → bf16 (better stability)")
print(f"• Warmup: Enhanced for stability")
print(f"• Early stopping patience: 3 → 5 (more stable training)")
print(f"• Save steps: 100 → 150 (less frequent for larger model)")
print(f"• Dataset: Full 2.5k samples (unchanged)")
print(f"• Epochs: 3 (unchanged)")
print("=" * 60)

from transformers import AutoTokenizer
from peft import PeftModel

# === CONFIG ===
CHECKPOINT_DIR = "/content/drive/MyDrive/final_stablelm_medical_checkpoints"  # or wherever you want to save
TOKENIZER_DIR = CHECKPOINT_DIR  # same directory is fine

# === SAVE TRAINED LoRA MODEL ===
print("💾 Saving LoRA fine-tuned model...")
trainer.save_model(CHECKPOINT_DIR)

# === SAVE TOKENIZER ===
print("💾 Saving tokenizer...")
tokenizer.save_pretrained(TOKENIZER_DIR)

print(f"✅ LoRA checkpoint saved to: {CHECKPOINT_DIR}")

import gc, os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# === CONFIGURATION ===
BASE_MODEL = "stabilityai/stablelm-3b-4e1t"  # your base model
LORA_DIR = "/content/drive/MyDrive/stablelm_medical_checkpoints/checkpoint-1650"  # directory with fine-tuned LoRA adapter
MERGED_DIR = "/content/drive/MyDrive/stablelm_merged"  # where to save merged model

# === CLEAR MEMORY BEFORE LOADING ===
gc.collect()
torch.cuda.empty_cache()

# === LOAD BASE MODEL ===
print("📦 Loading base StableLM 3B model...")
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True
)

# === LOAD LoRA WEIGHTS ===
print("🔗 Loading LoRA adapter...")
lora_model = PeftModel.from_pretrained(base_model, LORA_DIR)

# === MERGE LoRA INTO BASE MODEL ===
print("🔄 Merging LoRA into base model...")
merged_model = lora_model.merge_and_unload()

# === SAVE MERGED MODEL ===
print("💾 Saving merged model to disk...")
os.makedirs(MERGED_DIR, exist_ok=True)
merged_model.save_pretrained(MERGED_DIR, safe_serialization=True)

# === SAVE TOKENIZER ===
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
tokenizer.save_pretrained(MERGED_DIR)

print(f"✅ Merged model saved to: {MERGED_DIR}")

