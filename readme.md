Goal: execute arbitrary python code on a cloud server
The execution result of the main() function gets returned

POST: /execute: {"script": <string>} -> {"result": <return of main>, "stdout": <stdout of the script execution>}

[*] main function should return a JSON, if not -> throw exception
[*] if script has no "main func" -> throw exception
[*] light docker image 8080
[*] deploy to Google Cloud Run, add url to readme
[*] input validation
[*] safe script execution
[*] os, pandas, numpy should be accessible by the script
[*] use flask and nsjail

It took me nearly 3 hours to complete the task.
I got stuck while trying to run NsJail in Docker due to permission issues.

### Run
```
docker build -t stacksync .
docker run -p 8080:8080 stacksync
```

### Run tests
```
docker run --rm stacksync python -m pytest test_app.py -v
```