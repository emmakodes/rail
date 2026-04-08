FROM node:24-alpine

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

COPY package.json package-lock.json ./
RUN npm ci

COPY app ./app
COPY components ./components

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
