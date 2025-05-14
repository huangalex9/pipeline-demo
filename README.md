
## 📦 Setup & Deployment

### Local Development

1. Clone the repo  
   `git clone https://github.com/yourusername/skilltag.git`
2. Create a virtual environment  
   `python3 -m venv venv && source venv/bin/activate`
3. Install dependencies  
   `pip install -r requirements.txt`
4. Set environment variables for AWS keys and Bedrock config
5. Run the app  
   `flask run`

### AWS Deployment

1. Set up:
   - S3 Bucket
   - IAM roles for Transcribe, S3, and Bedrock
2. Create CodePipeline:
   - Source: GitHub
   - Build: (optional if no build step)
   - Deploy: CodeDeploy (EC2 or ECS target)
3. Configure `appspec.yml` and `deploy.sh` to restart Flask app

## ✅ To-Do

- Add user authentication (OAuth)
- Allow text uploads for faster tagging
- Enable download of tagged summaries
- Add error handling for failed transcriptions

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first.

## 📬 Contact

Created by [Your Name] – feel free to reach out via [LinkedIn](https://www.linkedin.com/in/yourprofile) or open an issue.

---

*This project uses Claude via Amazon Bedrock and assumes access to AWS credentials with appropriate permissions.*

