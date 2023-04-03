import git
from github import Github, GithubException
import subprocess
import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from config import registry,project_id,secret_name
# Load the Kubernetes configuration from default location
config.load_kube_config()
import jinja2
def get_latest_commit_for_branch(repo_name, branch_name, token):
    """
    Gets the latest commit for a specified branch in a GitHub repository using PyGithub.

    Parameters:
    repo_name (str): The name of the repository in the format owner/repo.
    branch_name (str): The name of the branch to get the latest commit for.
    token (str): A personal access token with the `repo` scope.

    Returns:
    str: The SHA of the latest commit for the specified branch, or None if the branch is not found.
    """
    # Initialize PyGithub with the personal access token
    g = Github(token)

    # Get the repository
    repo = g.get_repo(repo_name)

    # Try to get the latest commit for the specified branch
    try:
        commit = repo.get_branch(branch_name).commit.sha
    except GithubException as e:
        if e.status == 404:
            print(f"Branch {branch_name} not found in repository {repo_name}")
            commit = None
        else:
            raise e

    return commit

def slugify_text(text):
    # Convert all characters to lowercase
    text = text.lower()

    # Define a list of allowed characters (alphanumeric and hyphen)
    allowed_chars = list("abcdefghijklmnopqrstuvwxyz0123456789-")

    # Replace all non-allowed characters with hyphens
    slug = ""
    for char in text:
        if char in allowed_chars:
            slug += char
        else:
            slug += "-"
    
    # Remove any leading or trailing hyphens
    slug = slug.strip("-")

    return slug


def clone_repo_with_token(repo_url, token, branch_name, folder_path):
    """
    Clones a specific branch of a GitHub repository to a particular folder using a token.

    Parameters:
    repo_url (str): The URL of the repository to clone, in the format github.com/owner/repo.
    token (str): A personal access token with the `repo` scope.
    branch_name (str): The name of the branch to clone.
    folder_path (str): The local folder path to clone the repository to.

    Returns:
    None
    """
    # Set the token in the clone URL
    clone_url = f'https://{token}@{repo_url}'

    # Clone the repository using the token and branch name
    git.Repo.clone_from(clone_url, folder_path, branch=branch_name, depth=1)




def build_and_push_image(directory_path, project_id, image_name,image_tag, registry):
    # Build the Docker image
    build_command = f"gcloud builds submit --tag {registry}/{project_id}/{image_name}:{image_tag} {directory_path}"
    subprocess.run(build_command, shell=True, check=True)

    # Push the Docker image to the registry
    print(f"Successfully pushed image {registry}/{project_id}/{image_name}:{image_tag}")







# Load the YAML file containing the pod definition
def apply_config(pod_yaml,service_yaml,ingress_yaml,namespace):
    # with open('pod.yaml', 'r') as f:
    #     pod_yaml = yaml.load(f, Loader=yaml.FullLoader)

    # Create a Kubernetes API client
    apiv1 = client.CoreV1Api()
    api = client.AppsV1Api()
    iapi =  client.NetworkingV1Api()

    # Define the pod,service and ingressname
    pod_name = pod_yaml['metadata']['name']
    ingress_name = ingress_yaml['metadata']['name']
    service_name = service_yaml['metadata']['name']
    # Try to replace the pod
    try:
        api.replace_namespaced_deployment(name=pod_name, namespace=namespace, body=pod_yaml)
        print(f"Pod '{pod_name}' replaced successfully!")
    except ApiException as e:
        if e.status == 404:
            # Pod doesn't exist, create it instead
            api.create_namespaced_deployment(body=pod_yaml, namespace=namespace)
            print(f"Pod '{pod_name}' created successfully!")
            apiv1.create_namespaced_service(body=service_yaml, namespace='default')
            print(f"service '{service_name}' service successfully!")
            try:
                iapi.patch_namespaced_ingress(name=ingress_name, namespace=namespace, body=ingress_yaml)
                print(f"Ingress '{ingress_name}' replaced successfully!")
            except ApiException as e:
                if e.status == 404:
                    # Ingress doesn't exist, create it instead
                    iapi.create_namespaced_ingress(body=ingress_yaml, namespace=namespace)
                    print(f"Ingress '{ingress_name}' created successfully!")
                else:
                    # Other error occurred
                    print(f"Error: {e}")            
        else:
            # Other error occurred
            print(f"Error: {e}")



def deploy(repo,branch,token):
    commit_hash = get_latest_commit_for_branch(repo,branch,token)
    
    ##DELETE BRANCH IF commit_hash=None
    print(f"deploying {repo} : {branch} : {commit_hash}")
    image_tag = commit_hash[:10]
    clone_repo_with_token("github.com/"+repo,token,branch,'/tmp/'+image_tag)
    repo_name = repo.split('/')[-1]
    try:
        build_and_push_image('/tmp/'+image_tag,project_id,repo_name,image_tag,registry)
    except:
        subprocess.run("rm -rf /tmp/"+image_tag,shell=True)
        print("BUILD FAILED")
        return None
    #delete git repo
    subprocess.run("rm -rf /tmp/"+image_tag,shell=True)
    #read deployment,service,ingress template
    with open("deployment.yaml","r") as f:
        deployment_template = f.read()
    with open("service.yaml","r") as f:
        service_template = f.read()
    with open("ingress.yaml","r") as f:
        ingress_template = f.read()
    branch_slug = slugify_text(branch)
    environment = jinja2.Environment()
    deployment_template = environment.from_string(deployment_template)
    service_template = environment.from_string(service_template)
    ingress_template = environment.from_string(ingress_template)

    deployment_yaml = deployment_template.render(deployment_name=repo_name+'-'+branch_slug+'-deploy',image_uri=f'{registry}/{project_id}/{repo_name}:{image_tag}')
    service_yaml = service_template.render(service_name=repo_name+'-'+branch_slug+'-service',deployment_name=repo_name+'-'+branch_slug+'-deploy')
    ingress_yaml = ingress_template.render(ingress_name="sceptre1-ingress",domain="v2.tarang.dev",secret_name=secret_name,rules = [{"subdomain":branch_slug+'.'+"v2.tarang.dev","service_name":repo_name+'-'+branch_slug+'-service'}])
    
    deployment_yaml=yaml.load(deployment_yaml,Loader=yaml.Loader)
    service_yaml=yaml.load(service_yaml,Loader=yaml.Loader)
    ingress_yaml=yaml.load(ingress_yaml,Loader=yaml.Loader)
        
    apply_config(deployment_yaml,service_yaml,ingress_yaml,"default")
    #delete the image from google cloud registery
    subprocess.run(f"gcloud container images delete {registry}/{project_id}/{repo_name}:{image_tag} -q",shell=True)
    print("DEPLOYED")







###########
##########
# ########### f = open("ingress.yaml","r")
# >>> x = f.read()
# >>> i = template.render(branch_slug="a",image_uri="gcr.io/a/a",rules=[{"subdomain":"asd","service_name":"212"},{"subdomain":"a1sd","service_name":"212222"}])
# >>> template = environment.from_string(x)
# >>> i = template.render(branch_slug="a",image_uri="gcr.io/a/a",rules=[{"subdomain":"asd","service_name":"212"},{"subdomain":"a1sd","service_name":"212222"}])
# >>> print(i)