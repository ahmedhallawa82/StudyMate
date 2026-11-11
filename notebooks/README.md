# Notebooks (Google Colab)

| Notebook | What it does | Open in Colab |
|---|---|---|
| `StudyMate_Search_Models.ipynb` | Trains/evaluates TF-IDF, BM25, Hybrid and LSA search + the topic classifier on any course (built-in or uploaded PDFs) | [Open](https://colab.research.google.com/github/pikachu8240/StudyMate/blob/main/notebooks/StudyMate_Search_Models.ipynb) |
| `StudyMate_Image_Recognition.ipynb` | Extracts the images from lecture PDFs, trains a CNN (MobileNetV2 transfer learning on Colab) and builds an image-to-slide search index | [Open](https://colab.research.google.com/github/pikachu8240/StudyMate/blob/main/notebooks/StudyMate_Image_Recognition.ipynb) |

The notebooks stored here contain the outputs of a run on a CPU-only machine (`results_local/`). On Colab choose **Runtime ▸ Run all** to regenerate them
(the image notebook then uses ImageNet weights, which were not downloadable in the offline run).
