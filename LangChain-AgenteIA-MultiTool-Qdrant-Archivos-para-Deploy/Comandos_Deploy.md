## Loguearnos con Docker
docker login

## Construimos la Imagen y hacemos un Push en nuestro DockerHub
docker buildx build --platform linux/amd64 -t kevininofuentecolque/app-langchain-agente-inmobiliaria-backend-inofuente:latest --push .