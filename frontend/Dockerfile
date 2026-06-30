# Dev-mode container (Vite dev server). For prod, build static assets and serve
# behind nginx — see deploy/k8s for the production manifest.
FROM node:20-alpine

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
