FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY app ./app
COPY components ./components

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
