# Prompt-to-Structured-Medical-Report-Generation
'''
This repository hosts a project aimed at generating structured medical reports from natural language prompts using various Large Language Models (LLMs). The goal is to streamline the process of creating medical documentation, assisting healthcare professionals by transforming free-form text into organized, actionable reports.

## ✨ Features

* **Diverse LLM Integration:** Utilizes and experiments with multiple state-of-the-art Large Language Models, including:

  * Gemma 2B

  * Qwen

  * StableLM

  * TinyLlama 2.5/3

* **Structured Output:** Focuses on generating medical reports in a structured format, making the information easily parsable and usable.

* **Interactive Web UI:** Provides a user-friendly web interface built with Gradio for easy interaction, allowing users to input prompts and view generated reports directly.

* **Training Pipelines:** Includes scripts for fine-tuning and experimenting with different LLMs for optimal performance in medical report generation.

## 🚀 Technologies Used

* **Python:** The core programming language for the project.

* **Gradio:** For creating the interactive web-based user interface.

* **Hugging Face Transformers:** Likely used for loading, training, and inferring with various pre-trained LLMs.

* **PyTorch / TensorFlow:** Underlying deep learning frameworks for model operations (assumed based on LLM usage).

* **Large Language Models:**

  * Gemma 2B

  * Qwen

  * StableLM

  * TinyLlama

## ⚙️ Setup and Installation

To get this project up and running on your local machine, follow these steps:

1. **Clone the repository:**

```

git clone [https://github.com/AbhikrutiGNS/Prompt-to-Structured-Medical-Report-Generation.git](https://www.google.com/search?q=https://github.com/AbhikrutiGNS/Prompt-to-Structured-Medical-Report-Generation.git)
cd Prompt-to-Structured-Medical-Report-Generation

```

2. **Create a virtual environment (recommended)::**

```

python -m venv venv

# On Windows

.\\venv\\Scripts\\activate

# On macOS/Linux

source venv/bin/activate

```

3. **Install the required dependencies:**

* *Note: A `requirements.txt` file is highly recommended for listing all dependencies. If you create one, you can simply run `pip install -r requirements.txt`.*

* If `requirements.txt` is not available, you might need to install these manually:

```

pip install gradio transformers torch \# or tensorflow, depending on your setup

# You may also need specific libraries for each LLM, e.g., accelerate, bitsandbytes for quantization

```

## 🏃 Usage

Once the setup is complete, you can run the Gradio web interface to start generating medical reports.

1. **Activate your virtual environment** (if not already active):

```

# On Windows

.\\venv\\Scripts\\activate

# On macOS/Linux

source venv/bin/activate

```

2. **Run the Gradio application:**

```

python gradio\_ui.py

```

3. Open your web browser and navigate to the URL provided by Gradio (usually `http://127.0.0.1:7860/`).

4. In the Gradio interface, you can enter a natural language prompt (e.g., "Patient presented with severe headache and blurred vision. MRI showed a small lesion in the frontal lobe.") and click the "Generate Report" button to receive a structured medical report.

## 🤝 Contributing

Contributions are welcome! If you have suggestions for improvements, new features, or bug fixes, please feel free to:

1. Fork the repository.

2. Create a new branch (`git checkout -b feature/your-feature-name`).

3. Make your changes.

4. Commit your changes (`git commit -m 'Add new feature'`).

5. Push to the branch (`git push origin feature/your-feature-name`).

6. Open a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

## 📧 Contact

For any questions or inquiries, please reach out to Abhikruti GNS.
```
