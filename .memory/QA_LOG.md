# Q&A Log

## 2026-05-12

### Question

YOU MUST IMPLEMENT REAL MODEL IMPROVEMENT PIPELINE.

Current system works but accuracy is NOT sufficient:
- face recognition is unstable
- person detection is not robust
- object detection is weak
- action/motion understanding is minimal

THIS IS NOT A UI TASK.
THIS IS A DATA + MODEL QUALITY TASK.

Requirements included separate datasets and models per domain (face, person, object, action), training scripts, integration into workers, GPU/CPU rules, and validation without fake improvements.

### Answer

Implemented a real model-quality layer in the repository:

- `models/` for inference wrappers (face, detection, tracking, action, unified pipeline).
- `datasets/` for dataset registry and loaders.
- `training/` for `download_datasets.py`, `train_face.py`, `train_object.py`, `train_action.py`, and validation helpers.
- Configuration under `configs/models.json` and `training/configs/`.
- `workers/person/worker.py` upgraded to use the vision pipeline instead of Haar-only face detection and motion-only action heuristics when model backends are available.

Training uses strong pretrained checkpoints and fine-tuning; inference loads upgraded weights when present and otherwise uses stronger pretrained defaults.

---

### Question

Դա իսկ նախնայիր ամբողջական ծրեկտը։ Ծրեկտում կես համար ստեղծի հիշողության ֆայլեր, որտեղ գրես ամբողջովին ինչ է կատարվում, ինչ փոփոխություններ ես արել։ Անկումն հնարավոր է, որ արդեն կա հիշողության ֆայլ և միշտ, երբ որ ես քեզ հարց եմ տալիս, ծրագրում պետք է դու գրես այդ հիշողության ֆայլում և հարցը և պատասխանը։ Նաև հիշողության ֆայլի մեջ գրիր պարտադիր, որ Գիթհաբի անունը։ Ես հիմա քեզ կուղարքեմ Գիթհաբի մուտքը դեպի, որպեսզի դու ամբողջական հնարավորություն ունենաս այդ Գիթհաբում աշխատելու։ Այս պահին ծրեկտը Գիթհաբում չկա, ես քեզ ուղարքում եմ վես բազիտորի հարցում։ Միանգամից նաև այդ ռեպոզիտորում պահջիր իր ամբողջական ծրեկտը ամբողջությամբ, որիցի ամենիչից էլ կան աշխատի։

https://github.com/Samvel10/ai-detector

### Answer

Սկսեցի ամբողջական ծրագիրը memory ֆայլերով (`.memory/`)՝ GitHub անունով `Samvel10/ai-detector`, և նույն workspace-ից ամբողջ կոդը push արեցի remote repository-ին (`main` branch)։ Հարցերը/պատասխանները գրանցվում են `.memory/QA_LOG.md`-ում, փոփոխությունները՝ `.memory/CHANGELOG.md`-ում։
